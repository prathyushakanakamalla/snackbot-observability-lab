"""Streamlit chat UI.  Run:  streamlit run app_streamlit.py"""
import uuid

import streamlit as st

from snackbot import config
from snackbot.agent import SnackBot
from snackbot.feedback import log_feedback
from snackbot.tracing import setup_tracing

setup_tracing()  # PHASE 1: safe on every Streamlit re-run; only the first call does anything

st.set_page_config(page_title="SnackBot", page_icon="🥔")
st.title("🥔 SnackBot")
st.caption("Internal assistant for Crunchwell Foods (fictional) — AI observability lab, Phase 2")

if "history" not in st.session_state:
    st.session_state.history = []
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.span_ids = {}      # PHASE 2: history index of an answer -> its root span id
    st.session_state.feedback_sent = set()

with st.sidebar:
    model = st.text_input("Groq model", value=config.GROQ_MODEL)
    user_id = st.text_input("User id (shows on traces)", value="demo-user")
    if st.button("New conversation"):
        st.session_state.history = []
        st.session_state.span_ids = {}
        st.session_state.session_id = str(uuid.uuid4())
    st.caption(f"Tracing: **{config.TRACING}** · Phoenix: {config.PHOENIX_ENDPOINT}")
    st.caption(f"Session: `{st.session_state.session_id[:8]}…`")
    st.markdown("---")
    st.markdown("**Try:**\n- How many PTO days do I get in my first year?\n"
                "- Is CW-101 below its reorder point in Dallas?\n"
                "- What's the Q4 promo discount on Zesty Lime, in percent?")


def feedback_widget(index: int):
    """PHASE 2: thumbs up/down under an answer, sent to Phoenix as a HUMAN annotation."""
    span_id = st.session_state.span_ids.get(index)
    if not span_id:
        return
    choice = st.feedback("thumbs", key=f"fb_{st.session_state.session_id}_{index}")
    key = (span_id, choice)
    if choice is not None and key not in st.session_state.feedback_sent:
        if log_feedback(span_id, thumbs_up=(choice == 1), user_id=user_id):
            st.session_state.feedback_sent.add(key)
            st.toast("Feedback saved to Phoenix")


for i, turn in enumerate(st.session_state.history):
    with st.chat_message(turn["role"]):
        st.write(turn["content"])
        if turn["role"] == "assistant":
            feedback_widget(i)

if question := st.chat_input("Ask SnackBot…"):
    st.chat_message("user").write(question)
    with st.spinner("Thinking…"):
        result = SnackBot(model=model).answer(
            question, st.session_state.history,
            session_id=st.session_state.session_id, user_id=user_id,
            metadata={"interface": "streamlit"},
        )
    st.session_state.history += [{"role": "user", "content": question},
                                 {"role": "assistant", "content": result.answer}]
    answer_index = len(st.session_state.history) - 1
    st.session_state.span_ids[answer_index] = result.span_id
    with st.chat_message("assistant"):
        st.write(result.answer)
        if result.trace_id:
            st.caption(f"trace `{result.trace_id}`")
        feedback_widget(answer_index)
