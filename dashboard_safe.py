import streamlit as st
import subprocess

st.title("Echo Panel")
st.text("Golem:")
st.text(subprocess.getoutput("yagna payment status --network polygon --precise"))

col1, col2, col3 = st.columns(3)
if col1.button("Agent"):
    st.text(subprocess.getoutput("python3 echo_agent.py | tail -n10"))
if col2.button("Restart Golem"):
    subprocess.run(["systemctl", "--user", "restart", "golem-provider.service"])
    st.rerun()
if col3.button("Earnings"):
    try:
        with open("golem_earnings.json", "r") as f:
            st.text(f.read()[-500:])  # Last ~500 chars
    except:
        st.text("No log yet")
