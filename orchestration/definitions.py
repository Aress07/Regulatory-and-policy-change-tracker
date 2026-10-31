"""Dagster assets for the pipeline: raw_versions -> sections -> changes -> enrichments -> chunks
-> dbt_models, with freshness and enrichment asset checks and a weekly schedule.

Run the UI with the lineage graph:  dagster dev -f orchestration/definitions.py
Every asset calls the same functions as the CLI; no logic lives here.
"""

import subprocess
from datetime import datetime, timedelta

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    Definitions,
    MaterializeResult,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
)

from regtracker.common.config import get_settings, load_instruments
from regtracker.common.db import warehouse
from regtracker.common.http import PoliteClient


@asset(group_name="pipeline", description="Discover and download new consolidated versions.")
def raw_versions(context: AssetExecutionContext) -> MaterializeResult:
    from regtracker.ingest.fetch import ingest_all

    settings = get_settings()
    with warehouse(settings.warehouse_path) as con, PoliteClient(settings) as client:
        reports = ingest_all(con, client, load_instruments(), settings.raw_dir)
    errors = [f"{r.doc_id}: {r.error}" for r in reports if r.error]
    for e in errors:
        context.log.error(e)
    return MaterializeResult(
        metadata={
            "new_versions": sum(r.new for r in reports),
            "unavailable": sum(len(r.unavailable) for r in reports),
            "failed_instruments": len(errors),
        }
    )


@asset(deps=[raw_versions], group_name="pipeline", description="Parse XHTML into sections.")
def sections() -> MaterializeResult:
    from regtracker.parse.stage import parse_pending

    with warehouse(get_settings().warehouse_path) as con:
        reports = parse_pending(con)
    return MaterializeResult(
        metadata={
            "versions_parsed": sum(not r.error for r in reports),
            "failed": sum(bool(r.error) for r in reports),
        }
    )


@asset(deps=[sections], group_name="pipeline", description="Deterministic section diff.")
def changes() -> MaterializeResult:
    from regtracker.diff.stage import diff_all

    with warehouse(get_settings().warehouse_path) as con:
        reports = diff_all(con)
    return MaterializeResult(metadata={"new_changes": sum(r.new for r in reports)})


@asset(deps=[changes], group_name="pipeline", description="LLM explanations (budget-aware).")
def enrichments() -> MaterializeResult:
    from regtracker.enrich.enrich import enrich_pending
    from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config

    settings = get_settings()
    config = load_llm_config(settings)
    with warehouse(settings.warehouse_path) as con:
        report = enrich_pending(
            con, OpenAICompatibleLLM(settings, config, con), config, config.summary_model
        )
    return MaterializeResult(
        metadata={
            "succeeded": report.succeeded,
            "failed": report.failed,
            "llm_calls": report.llm_calls,
            "tokens": report.tokens,
            "stopped_reason": report.stopped_reason or "",
        }
    )


@asset(deps=[sections], group_name="pipeline", description="Chunks and E5 embeddings.")
def chunks() -> MaterializeResult:
    from regtracker.index.embed import E5Embedder
    from regtracker.index.stage import build_index
    from regtracker.rag.answer import load_rag_config

    with warehouse(get_settings().warehouse_path) as con:
        report = build_index(con, E5Embedder(), load_rag_config().chunk_max_tokens)
    return MaterializeResult(metadata={"chunks": report.chunks, "embedded": report.embedded})


@asset(
    deps=[changes, enrichments], group_name="pipeline", description="dbt build (models + tests)."
)
def dbt_models(context: AssetExecutionContext) -> MaterializeResult:
    result = subprocess.run(
        ["dbt", "build", "--project-dir", "dbt", "--profiles-dir", "dbt"],
        capture_output=True,
        text=True,
        check=False,
    )
    context.log.info(result.stdout[-4000:])
    if result.returncode != 0:
        raise RuntimeError(f"dbt build failed:\n{result.stdout[-2000:]}")
    return MaterializeResult(metadata={"dbt": "build passed"})


@asset_check(asset=raw_versions, description="Latest successful ingest is at most 8 days old.")
def ingest_is_fresh() -> AssetCheckResult:
    with warehouse(get_settings().warehouse_path) as con:
        row = con.execute(
            "SELECT max(finished_at) FROM pipeline_runs "
            "WHERE stage LIKE 'ingest:%' AND status = 'success'"
        ).fetchone()
    last = row[0] if row else None
    fresh = last is not None and datetime.now() - last <= timedelta(days=8)
    return AssetCheckResult(passed=fresh, metadata={"last_successful_ingest": str(last)})


@asset_check(asset=enrichments, description="No change is left with only failed enrichments.")
def no_failed_enrichments() -> AssetCheckResult:
    with warehouse(get_settings().warehouse_path) as con:
        row = con.execute(
            "SELECT count(DISTINCT change_id) FROM enrichments e WHERE status = 'failed' "
            "AND NOT EXISTS (SELECT 1 FROM enrichments s WHERE s.change_id = e.change_id "
            "AND s.status = 'success')"
        ).fetchone()
    failed = int(row[0]) if row else 0
    return AssetCheckResult(passed=failed == 0, metadata={"failed_changes": failed})


pipeline_job = define_asset_job("weekly_pipeline", selection="*")

defs = Definitions(
    assets=[raw_versions, sections, changes, enrichments, chunks, dbt_models],
    asset_checks=[ingest_is_fresh, no_failed_enrichments],
    jobs=[pipeline_job],
    schedules=[ScheduleDefinition(job=pipeline_job, cron_schedule="0 6 * * 1")],  # Mondays 06:00
)
