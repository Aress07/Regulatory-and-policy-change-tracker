from datetime import date

import streamlit as st
from shared import AI_BADGE, warehouse_path

from regtracker.common.config import get_settings
from regtracker.rag.answer import Answerer, load_rag_config

SESSION_CAP = 10  # questions per browser session
DAILY_CAP = 200  # questions per day across all users (protects the shared free-tier key)


@st.cache_resource(show_spinner="Loading the search index and embedding model...")
def answerer() -> Answerer:
    import duckdb

    from regtracker.common.db import init_schema
    from regtracker.enrich.llm_client import OpenAICompatibleLLM, load_llm_config
    from regtracker.index.embed import E5Embedder
    from regtracker.index.search import SearchIndex
    from regtracker.rag.answer import source_urls

    settings = get_settings()
    con = duckdb.connect(warehouse_path(), read_only=True)
    try:
        index, urls = SearchIndex.load(con), source_urls(con)
    finally:
        con.close()
    llm_config = load_llm_config(settings)
    calls_con = duckdb.connect(":memory:")  # LLM call log and daily budget for this process
    init_schema(calls_con)
    llm = OpenAICompatibleLLM(settings, llm_config, calls_con) if settings.llm_api_key else None
    return Answerer(index, E5Embedder(), llm, llm_config.summary_model, urls, load_rag_config())


@st.cache_resource
def daily_counter() -> dict[date, int]:
    return {}


st.markdown(
    f"Answers are {AI_BADGE} from the latest consolidated texts only, and every sentence must "
    "cite a passage. When the evidence is weak, you get the closest passages instead."
)
with st.form("ask"):
    question = st.text_input(
        "Question",
        max_chars=load_rag_config().max_question_chars,
        placeholder="Within how many hours must a data breach be notified?",
    )
    submitted = st.form_submit_button("Ask", icon=":material/send:")

if not submitted or not question.strip():
    st.stop()

counter = daily_counter()
today = date.today()
over_cap = st.session_state.questions_asked >= SESSION_CAP or counter.get(today, 0) >= DAILY_CAP
rag = answerer()
if over_cap:
    rag = Answerer(rag.index, rag.embedder, None, rag.model, rag.urls, rag.config)
else:
    st.session_state.questions_asked += 1
    counter[today] = counter.get(today, 0) + 1

with st.spinner("Searching..."):
    result = rag.ask(question)

if result.status == "answered" and result.answer:
    with st.container(border=True):
        st.markdown(f"{result.answer}  \n{AI_BADGE} :gray-badge[confidence: {result.confidence}]")
        for cit in result.citations:
            st.markdown(f"[{cit.n}] [{cit.breadcrumb}]({cit.source_url})")
else:
    message = {
        "not_found": "The retrieved passages do not answer this question.",
        "not_enough_evidence": "Not enough evidence in the tracked texts to answer.",
        "rejected_invalid_citations": "The generated answer was rejected because its citations "
        "could not be verified.",
        "retrieval_only": "Answer generation is unavailable right now.",
    }.get(result.status, "No answer.")
    if over_cap:
        message = "Question limit reached for now; showing the most relevant passages instead."
    st.info(message + " Here are the closest passages.", icon=":material/info:")

with st.expander("Retrieved passages", expanded=result.status != "answered"):
    for n, hit in enumerate(result.retrieved, start=1):
        st.markdown(f"**[{n}] {hit.breadcrumb}** :gray-badge[similarity {hit.cosine:.2f}]")
        st.text(hit.text.split("\n", 1)[-1])
