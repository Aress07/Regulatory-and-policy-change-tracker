"""EU Regulation Change Tracker dashboard. Run: streamlit run dashboard/app.py"""

import streamlit as st
from shared import DISCLAIMER

st.set_page_config(
    page_title="EU Regulation Change Tracker", page_icon=":material/gavel:", layout="wide"
)

if "selected_change" not in st.session_state:
    st.session_state.selected_change = None
if "questions_asked" not in st.session_state:
    st.session_state.questions_asked = 0

page = st.navigation(
    {
        "": [
            st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:"),
            st.Page("app_pages/timeline.py", title="Change timeline", icon=":material/timeline:"),
            st.Page("app_pages/detail.py", title="Change detail", icon=":material/difference:"),
            st.Page("app_pages/trends.py", title="Topic trends", icon=":material/insights:"),
            st.Page("app_pages/since.py", title="Since I last looked", icon=":material/history:"),
            st.Page("app_pages/ask.py", title="Ask", icon=":material/question_answer:"),
        ],
        "Operations": [
            st.Page(
                "app_pages/health.py", title="Pipeline health", icon=":material/monitor_heart:"
            ),
        ],
    },
    position="top",
)

st.title(page.title)
# Rendered before the page so it shows even when a page stops early (st.stop()).
st.caption(DISCLAIMER)
page.run()
