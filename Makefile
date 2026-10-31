.PHONY: setup lint format typecheck test check init ingest parse diff enrich index app api

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

app:
	streamlit run dashboard/app.py

api:
	uvicorn regtracker.api.main:app --reload
