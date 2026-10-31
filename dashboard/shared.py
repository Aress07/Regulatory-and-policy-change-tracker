"""Cached data access and shared UI bits for dashboard pages (SQL lives in regtracker.app)."""

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, TypeVar

import duckdb
import pandas as pd
import streamlit as st

from regtracker.app import queries
from regtracker.app.snapshot import resolve_warehouse
from regtracker.common.config import get_settings

DISCLAIMER = (
    "**Not legal advice.** Summaries, tags and answers are AI-generated and can be wrong. "
    "Always check the official text on EUR-Lex."
)
AI_BADGE = ":violet-badge[:material/auto_awesome: AI-generated]"
SYNTHETIC_BADGE = ":orange-badge[:material/science: Synthetic test data]"
IMPACT_COLOR = {"high": "red", "medium": "orange", "low": "blue"}

T = TypeVar("T")


@st.cache_resource
def warehouse_path() -> str:
    settings = get_settings()
    import os

    path = resolve_warehouse(
        Path(settings.warehouse_path), os.environ.get("HF_DATASET_REPO"), os.environ.get("HF_TOKEN")
    )
    return str(path)


def _query(fn: Callable[[duckdb.DuckDBPyConnection], T]) -> T:
    con = duckdb.connect(warehouse_path(), read_only=True)
    try:
        return fn(con)
    finally:
        con.close()


@st.cache_data(ttl="10m", show_spinner=False)
def load_changes() -> pd.DataFrame:
    return _query(queries.changes)


@st.cache_data(ttl="10m", show_spinner=False)
def load_documents() -> pd.DataFrame:
    return _query(queries.documents)


@st.cache_data(ttl="10m", show_spinner=False)
def load_freshness() -> dict[str, Any]:
    return _query(queries.freshness)


@st.cache_data(ttl="10m", show_spinner=False)
def load_runs() -> pd.DataFrame:
    return _query(queries.pipeline_runs)


@st.cache_data(ttl="10m", show_spinner=False)
def load_llm_usage() -> pd.DataFrame:
    return _query(queries.llm_usage)


@st.cache_data(ttl="10m", show_spinner=False, max_entries=200)
def load_change_detail(change_id: str) -> dict[str, Any] | None:
    return _query(lambda con: queries.change_detail(con, change_id))


def impact_badge(impact: str | None) -> str:
    if not impact:
        return ":gray-badge[not rated]"
    return f":{IMPACT_COLOR[impact]}-badge[{impact} impact]"


def freshness_banner() -> None:
    fresh = load_freshness()
    last = fresh["last_successful_ingest"]
    if last is None:
        st.warning("No successful ingestion recorded yet.", icon=":material/warning:")
        return
    days = (pd.Timestamp.now() - pd.Timestamp(last)).days
    text = f"Last successful ingest: {pd.Timestamp(last):%Y-%m-%d %H:%M} UTC ({days} days ago)"
    if days > 8:
        st.warning(text + ". Data may be stale.", icon=":material/schedule:")
    else:
        st.caption(f":material/check_circle: {text}")


def open_change(change_id: str) -> None:
    st.session_state.selected_change = change_id
    st.switch_page("app_pages/detail.py")


def today() -> date:
    return pd.Timestamp.now().date()
