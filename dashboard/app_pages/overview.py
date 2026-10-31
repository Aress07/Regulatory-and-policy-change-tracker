import pandas as pd
import streamlit as st
from shared import freshness_banner, load_changes, load_documents, today

freshness_banner()

changes = load_changes()
docs = load_documents()
real = changes[~changes["is_synthetic"]]
dates = pd.to_datetime(real["to_date"]).dt.date
latest_change = dates.max() if not real.empty else None

with st.container(horizontal=True):
    st.metric("Instruments tracked", len(docs), border=True)
    st.metric("Versions parsed", int(docs["versions"].sum()), border=True)
    st.metric("Changes detected", len(real), border=True)
    st.metric("High-impact changes", int((real["impact"] == "high").sum()), border=True)
    st.metric(
        "Changes enriched",
        f"{int(real['is_enriched'].sum())} / {len(real)}",
        border=True,
    )

recent = real[dates >= today() - pd.Timedelta(days=90)]
if recent.empty and latest_change is not None:
    st.info(
        f"No changes in the last 90 days. EU acts are amended rarely; the most recent "
        f"consolidated change in this corpus is from {latest_change:%d %B %Y}.",
        icon=":material/info:",
    )

with st.container(border=True):
    st.subheader("Instruments")
    st.dataframe(
        docs[
            [
                "instrument",
                "doc_type",
                "celex_base",
                "versions",
                "latest_version",
                "repealed",
                "source_url",
            ]
        ],
        hide_index=True,
        column_config={
            "instrument": "Instrument",
            "doc_type": "Type",
            "celex_base": "CELEX",
            "versions": st.column_config.NumberColumn("Versions"),
            "latest_version": st.column_config.DateColumn("Latest version"),
            "repealed": st.column_config.CheckboxColumn("Repealed"),
            "source_url": st.column_config.LinkColumn("Official text", display_text="EUR-Lex"),
        },
        alt="Tracked legal instruments",
    )

with st.container(border=True):
    st.subheader("Changes per instrument")
    per_doc = real.groupby(["instrument", "change_type"]).size().reset_index(name="changes")
    if per_doc.empty:
        st.caption("No changes detected yet.")
    else:
        st.bar_chart(
            per_doc, x="instrument", y="changes", color="change_type", horizontal=True,
            alt="Detected changes per instrument by change type",
        )  # fmt: skip
