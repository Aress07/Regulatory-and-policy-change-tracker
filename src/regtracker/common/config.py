"""Settings loaded from environment / .env. Never hardcode secrets."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Instrument(BaseModel):
    doc_id: str
    celex_base: str
    doc_type: str
    name: str | None = None  # short display name, e.g. "GDPR"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    warehouse_path: Path = Path("data/warehouse.duckdb")
    raw_dir: Path = Path("data/raw")
    user_agent: str = "eu-reg-tracker/0.1 (contact: you@example.com)"
    requests_per_second: float = 1.0

    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""
    llm_model_classify: str = ""
    llm_model_summary: str = ""
    llm_tpm: int = 6000
    llm_daily_token_budget: int = 150_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_instruments(path: Path = Path("configs/sources.yml")) -> list[Instrument]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Instrument(**item) for item in data["instruments"]]
