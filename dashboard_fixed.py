import streamlit as st
import subprocess

st.title("Echo Control Panel")
st.text("Golem:")
st.text(subprocess.getoutput("yagna payment status --network polygon --precise"))

if st.button("Agent Report"):
    st.text(subprocess.getoutput("python3 echo_agent.py | tail -n15"))

if st.button("Golem Restart"):
    subprocess.run(["systemctl", "--user", "restart", "golem-provider.service"])
    st.success("Restarted – Check logs!")

if st.button("Earnings Tail"):
    with open("golem_earnings.json") as f:
        st.text("".join(f.readlines()[-10:]))
