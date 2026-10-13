"""Streamlit chat UI.  Run:  streamlit run app_streamlit.py"""
import streamlit as st

from snackbot import config
from snackbot.agent import SnackBot

st.set_page_config(page_title="SnackBot", page_icon="🥔")
st.title("🥔 SnackBot")
st.caption("Internal assistant for Crunchwell Foods (fictional) — AI observability lab, Phase 0")

with st.sidebar:
    model = st.text_input("Groq model", value=config.GROQ_MODEL)
    if st.button("New conversation"):
        st.session_state.history = []
    st.markdown("---")
    st.markdown("**Try:**\n- How many PTO days do I get in my first year?\n"
                "- Is CW-101 below its reorder point in Dallas?\n"
                "- What's the Q4 promo discount on Zesty Lime, in percent?")

if "history" not in st.session_state:
    st.session_state.history = []

for turn in st.session_state.history:
    st.chat_message(turn["role"]).write(turn["content"])

if question := st.chat_input("Ask SnackBot…"):
    st.chat_message("user").write(question)
    with st.spinner("Thinking…"):
        result = SnackBot(model=model).answer(question, st.session_state.history)
    st.chat_message("assistant").write(result.answer)
    st.session_state.history += [{"role": "user", "content": question},
                                 {"role": "assistant", "content": result.answer}]
