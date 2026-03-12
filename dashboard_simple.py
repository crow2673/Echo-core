import streamlit as st
import subprocess

st.title("Echo Control Panel")
st.text("Golem Live:")
st.text(subprocess.getoutput("yagna payment status --network polygon --precise"))

if st.button("Agent Report"):
    st.text(subprocess.getoutput("python3 echo_agent.py"))

st.button("Golem Restart", on_click=lambda: st.subheader("Restarted!")(["systemctl", "--user", "restart", "golem-provider"]))
st.button("Earnings Tail", on_click=lambda: st.text(open("golem_earnings.json").readlines()[-10:]))
