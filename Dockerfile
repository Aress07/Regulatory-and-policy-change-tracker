# One container: FastAPI serves the API (/api) and the built React app.
# Built for Hugging Face Spaces (Docker SDK, port 7860); runs anywhere Docker does.

# --- frontend build ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- runtime ----------------------------------------------------------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist HF_HOME=/app/.cache/huggingface
WORKDIR /app

# CPU-only torch keeps the image far smaller than the default CUDA build.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY pyproject.toml README.md ./
COPY src/ src/
COPY configs/ configs/
RUN pip install ".[llm,ml,app]"

COPY --from=frontend /frontend/dist frontend/dist

# Download the embedding model at build time so the first question is not slow.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

# The warehouse comes from the Hugging Face dataset snapshot (HF_DATASET_REPO) at startup,
# or mount one at /app/data/warehouse.duckdb.
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 7860
CMD ["uvicorn", "regtracker.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
