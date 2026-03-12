import os, json, time, glob, subprocess
import streamlit as st

st.set_page_config(layout="wide")
st.title("Echo Dashboard (AI / Vision / Memory / Spy)")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Live Scan (e_scan.sh)")
    if st.button("Run e_scan.sh"):
        out = subprocess.getoutput("./e_scan.sh")
        st.text_area("scan", out, height=350)

    st.subheader("Recent Screens (static files)")
    screens = sorted(glob.glob("screen_*.png"), key=os.path.getmtime, reverse=True)[:6]
    if os.path.exists("screen_latest.png"):
        screens = ["screen_latest.png"] + screens
    screens = list(dict.fromkeys(screens))
    if not screens:
        st.info("No screen_*.png found yet.")
    for p in screens[:6]:
        st.image(p, caption=p, width='stretch')

with col2:
    st.subheader("Agent Memory (echo_memory_ai.json)")
    if os.path.exists("echo_memory_ai.json"):
        try:
            mem = json.load(open("echo_memory_ai.json"))
            st.json(mem)
        except Exception as e:
            st.error(f"Failed to load memory: {e}")
    else:
        st.info("echo_memory_ai.json not created yet (start echo_agi_lite.py).")

    st.subheader("Activity Log (tail)")
    log_path = "echo_activity.log"
    if os.path.exists(log_path):
        lines = open(log_path).read().splitlines()[-80:]
        st.text("\n".join(lines))
    else:
        st.info("echo_activity.log missing.")

st.caption("Note: Vision capture is not included here; dashboard only displays existing PNGs.")
