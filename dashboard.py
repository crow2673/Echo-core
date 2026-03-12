import streamlit as st
import pandas as pd
import subprocess
import psutil
import plotly.graph_objs as go

st.set_page_config(layout="wide")
st.title("🌾 Echo Farm LIVE")

tabs = st.tabs(["Metrics", "Processes", "GLM Graph", "Logs"])

with tabs[0]:
    col1, col2 = st.columns(2)
    col1.metric("GLM", "0.0000", "Ramp")
    col2.metric("Memory", "200+", "Trades")
    if st.button("Ramp"):
        st.balloons()

with tabs[1]:
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
        if any(x in p.info['name'].lower() for x in ['echo', 'ollama', 'yagna', 'streamlit']):
            procs.append({k: v for k, v in p.info.items()})
    st.dataframe(procs)

with tabs[2]:
    try:
        status = subprocess.check_output(['yagna', 'payment', 'status'], text=True)
        lines = status.split('\n')
        
        glml = next((line.split()[-1] for line in lines if 'GLM' in line or 'tGLM' in line), '0')
        
        # Handle conversion correctly
        try:
            glml_value = float(glml.replace('GLM', '').replace('tGLM', '').strip())
        except ValueError:
            glml_value = 0.0
        
        fig = go.Figure(data=[go.Bar(x=['Earnings'], y=[glml_value])])
        st.plotly_chart(fig)
        st.text(status)
    except Exception as e:
        st.error(f"Could not parse GLM value: {e}")

with tabs[3]:
    try:
        log_output = subprocess.check_output(
            ['journalctl', '--user', '-u', 'echo.service', '--lines=20'], 
            text=True
        )
        st.code(log_output)
    except Exception as e:
        st.error(f"Log read error: {e}")

st.success("24/7 Farm")
