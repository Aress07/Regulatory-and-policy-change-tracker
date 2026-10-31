# ADR-004: FastAPI + React web app instead of Streamlit

**Status:** accepted (2026-10-31). Supersedes the Streamlit dashboard from the original plan.

## Context
The first dashboard was a 7-page Streamlit app. The project owner asked for a FastAPI backend
with a React frontend instead. A FastAPI service with `/ask` already existed.

## Decision
- **Backend:** extend `src/regtracker/api/main.py` with read-only JSON endpoints under `/api`
  (`overview`, `documents`, `changes` with filters, `changes/{id}`, `trends`, `runs`,
  `llm-usage`, `freshness`, `meta`, `ask`). SQL stays in `regtracker.app.queries`, now returning
  plain records (pandas is no longer needed).
- **Frontend:** `frontend/`, React 18 + TypeScript + Vite, react-router, recharts (lazy-loaded so
  only chart pages download it). Filters live in the URL so views can be shared.
- **One deployable:** FastAPI serves the built app from `frontend/dist` with a single-page-app
  fallback, so the whole product is one Docker image (`Dockerfile`), deployable for free on a
  Hugging Face Space (Docker SDK). Streamlit Community Cloud is no longer used.

## Consequences
+ A real API contract (OpenAPI at `/api/docs`) that other clients can use; typed frontend.
+ Faster, more controllable UI; deep links to changes and filtered timelines.
+ CI covers the frontend (typecheck, Vitest, build) and builds and smoke-tests the image.
- Two toolchains (Python and Node 20+) for development.
- More code than the Streamlit pages; UI state (filters, remembered dates) is now our code.
- `/ask` rate limits are in-process: fine for one container, not for horizontal scaling.
