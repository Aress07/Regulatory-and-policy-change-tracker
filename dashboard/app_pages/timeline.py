import pandas as pd
import streamlit as st
from shared import load_changes, open_change

from regtracker.enrich.schemas import SECTORS, TOPICS

changes = load_changes()
if changes.empty:
    st.info(
        "No changes detected yet. Run the pipeline: ingest, parse, diff.", icon=":material/info:"
    )
    st.stop()

with st.container(border=True):
    left, right = st.columns(2)
    with left:
        instruments = st.multiselect("Instrument", sorted(changes["instrument"].unique()))
        topics = st.multiselect("Topic (AI-generated)", TOPICS)
        sectors = st.multiselect("Sector (AI-generated)", SECTORS)
    with right:
        impacts = st.pills(
            "Impact (AI-generated)", ["high", "medium", "low", "not rated"], selection_mode="multi"
        )
        kinds = st.pills(
            "Change type", ["added", "removed", "modified", "renumbered"], selection_mode="multi"
        )
        dates = pd.to_datetime(changes["to_date"]).dt.date
        date_range = st.date_input("Version date", value=(dates.min(), dates.max()))
        show_synthetic = st.toggle("Include synthetic test changes", value=False)

view = changes.copy()
if instruments:
    view = view[view["instrument"].isin(instruments)]
if topics:
    view = view[view["topics"].apply(lambda t: t is not None and any(x in t for x in topics))]
if sectors:
    view = view[view["sectors"].apply(lambda s: s is not None and any(x in s for x in sectors))]
if impacts:
    wanted = {i for i in impacts if i != "not rated"}
    view = view[view["impact"].isin(wanted) | ("not rated" in impacts and view["impact"].isna())]
if kinds:
    view = view[view["change_type"].isin(kinds)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    d = pd.to_datetime(view["to_date"]).dt.date
    view = view[(d >= date_range[0]) & (d <= date_range[1])]
if not show_synthetic:
    view = view[~view["is_synthetic"]]

st.caption(f"{len(view)} of {len(changes)} changes. Select a row to open its detail.")
event = st.dataframe(
    view[
        [
            "to_date",
            "instrument",
            "section_key",
            "heading",
            "change_type",
            "impact",
            "summary",
            "is_synthetic",
        ]
    ],
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "to_date": st.column_config.DateColumn("Version date"),
        "instrument": "Instrument",
        "section_key": "Section",
        "heading": "Heading",
        "change_type": "Type",
        "impact": "Impact (AI)",
        "summary": st.column_config.TextColumn("Summary (AI-generated)", width="large"),
        "is_synthetic": st.column_config.CheckboxColumn("Synthetic"),
    },
    alt="Detected changes",
)
if event.selection.rows:
    open_change(view.iloc[event.selection.rows[0]]["change_id"])
