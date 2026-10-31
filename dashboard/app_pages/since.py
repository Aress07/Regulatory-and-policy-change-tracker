import pandas as pd
import streamlit as st
from shared import AI_BADGE, SYNTHETIC_BADGE, impact_badge, load_changes, open_change, today

from regtracker.app.queries import changes_since

changes = load_changes()
since = st.date_input(
    "Show changes in versions dated on or after",
    value=today() - pd.Timedelta(days=365 * 3),
    max_value=today(),
)
view = changes_since(changes[~changes["is_synthetic"]], since)

if view.empty:
    st.success(f"No changes since {since:%d %B %Y}.", icon=":material/check_circle:")
    st.stop()

st.caption(f"{len(view)} changes since {since:%d %B %Y}. Summaries are {AI_BADGE}.")
for instrument, group in view.groupby("instrument", sort=True):
    with st.expander(f"{instrument} ({len(group)} changes)", expanded=len(view) <= 20):
        for row in group.itertuples():
            badges = f":gray-badge[{row.change_type}] {impact_badge(row.impact)}"
            if row.is_synthetic:
                badges += f" {SYNTHETIC_BADGE}"
            st.markdown(f"**{row.section_key}** {row.heading or ''} {badges}")
            st.caption(row.summary or "No AI summary yet.")
            st.button(
                "Open detail", key=f"open-{row.change_id}", icon=":material/difference:",
                on_click=open_change, args=(row.change_id,),
            )  # fmt: skip
