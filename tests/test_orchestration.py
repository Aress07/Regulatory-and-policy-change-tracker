import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("dagster")


def test_dagster_definitions_load() -> None:
    path = Path(__file__).parent.parent / "orchestration" / "definitions.py"
    spec = importlib.util.spec_from_file_location("definitions", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = module.defs.get_repository_def()

    assets = {k.to_user_string() for k in repo.asset_graph.get_all_asset_keys()}
    assert assets == {"raw_versions", "sections", "changes", "enrichments", "chunks", "dbt_models"}
    assert len(list(repo.asset_graph.asset_check_keys)) == 2
    assert [s.cron_schedule for s in repo.schedule_defs] == ["0 6 * * 1"]
