.PHONY: setup lint format typecheck test check init ingest parse diff enrich index dbt dbt-fixture app api frontend frontend-dev pipeline snapshot dagster eval demo docker

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

# Frontend: build once, then the API serves it at http://localhost:8000
frontend:
	cd frontend && npm ci && npm run build

# Development: API with reload on :8000, Vite dev server (proxying /api) on :5173
frontend-dev:
	cd frontend && npm run dev

# Whole app on a warehouse built from fixtures: no network, no API key needed
demo: frontend
	regtracker fixture-db --out data/fixture.duckdb
	WAREHOUSE_PATH=data/fixture.duckdb uvicorn regtracker.api.main:app --port 8000

app: frontend api

docker:
	docker build -t regtracker .

api:
	uvicorn regtracker.api.main:app --reload --port 8000
