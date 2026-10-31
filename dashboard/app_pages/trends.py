import altair as alt
import streamlit as st
from shared import AI_BADGE, load_changes

from regtracker.app.queries import topic_counts

st.markdown(f"Topics are assigned by the LLM {AI_BADGE}; synthetic test changes are excluded.")
counts = topic_counts(load_changes())
if counts.empty:
    st.info("No enriched changes yet. Run `regtracker enrich`.", icon=":material/info:")
    st.stop()

with st.container(border=True):
    st.subheader("Changes per topic over time")
    per_year = counts.groupby(["year", "topic"], as_index=False)["changes"].sum()
    per_year["year"] = per_year["year"].astype(str)
    st.bar_chart(per_year, x="year", y="changes", color="topic", alt="Changes per topic per year")

with st.container(border=True):
    st.subheader("Instrument by topic")
    grid = counts.groupby(["instrument", "topic"], as_index=False)["changes"].sum()
    chart = (
        alt.Chart(grid)
        .mark_rect()
        .encode(
            x=alt.X("topic:N", title="Topic"),
            y=alt.Y("instrument:N", title=None),
            color=alt.Color("changes:Q", title="Changes", scale=alt.Scale(scheme="blues")),
            tooltip=["instrument", "topic", "changes"],
        )
    )
    st.altair_chart(chart, alt="Heatmap of changes by instrument and topic")
