.PHONY: setup lint format typecheck test check init ingest parse diff enrich index dbt dbt-fixture app api pipeline snapshot dagster eval demo

setup:
	uv sync --all-extras || (python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev,llm,ml,app,pipeline]")
	pre-commit install

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy src

test:
	pytest

check: lint typecheck test

init:
	regtracker init-db

ingest parse diff enrich index:
	regtracker $@

dbt:
	dbt build --project-dir dbt --profiles-dir dbt

# dbt against a database built from tests/fixtures (what CI runs; no network)
dbt-fixture:
	regtracker fixture-db --out data/fixture.duckdb
	WAREHOUSE_PATH=data/fixture.duckdb dbt build --project-dir dbt --profiles-dir dbt

# Full local pipeline (enrichment uses the LLM budget; reruns are cached)
pipeline: ingest parse diff enrich index dbt

snapshot:
	regtracker snapshot

dagster:
	dagster dev -f orchestration/definitions.py

eval:
	python eval/run_eval.py --suite all --out eval/reports/

# Dashboard on a warehouse built from fixtures: no network, no API key needed
demo:
	regtracker fixture-db --out data/fixture.duckdb
	WAREHOUSE_PATH=data/fixture.duckdb streamlit run dashboard/app.py

app:
	streamlit run dashboard/app.py

api:
	uvicorn regtracker.api.main:app --reload
