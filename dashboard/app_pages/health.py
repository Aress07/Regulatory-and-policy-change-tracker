import streamlit as st
from shared import freshness_banner, load_freshness, load_llm_usage, load_runs

freshness_banner()
runs = load_runs()
fresh = load_freshness()

with st.container(horizontal=True):
    st.metric("Stage runs logged", len(runs), border=True)
    st.metric("Failures (last 7 days)", int(fresh["failures_last_7_days"]), border=True)
    st.metric(
        "Distinct pipeline runs", runs["run_id"].nunique() if not runs.empty else 0, border=True
    )

with st.container(border=True):
    st.subheader("LLM usage and shadow cost")
    st.caption(
        "Shadow cost = tokens priced at public list prices (configs/llm.yml); the free tier "
        "actually costs $0."
    )
    usage = load_llm_usage()
    if usage.empty:
        st.caption("No enrichment runs yet.")
    else:
        st.dataframe(usage, hide_index=True, alt="LLM usage per model and prompt version")

with st.container(border=True):
    st.subheader("Recent stage runs")
    stages = sorted(runs["stage"].unique()) if not runs.empty else []
    chosen = st.pills("Stage", stages, selection_mode="multi")
    only_failed = st.toggle("Failures only")
    view = runs
    if chosen:
        view = view[view["stage"].isin(chosen)]
    if only_failed:
        view = view[view["status"] == "failed"]
    st.dataframe(
        view.drop(columns=["run_id"]),
        hide_index=True,
        column_config={
            "started_at": st.column_config.DatetimeColumn("Started", format="YYYY-MM-DD HH:mm"),
            "finished_at": None,
            "seconds": st.column_config.NumberColumn("Seconds", format="%.1f"),
            "error": st.column_config.TextColumn("Error", width="large"),
        },
        alt="Pipeline stage runs",
    )
