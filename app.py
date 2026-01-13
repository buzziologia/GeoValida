# app.py (Raiz)
import streamlit as st
from main import GeoValidaManager
from src.interface.dashboard import render_dashboard

# Mantém o Manager vivo entre cliques no Streamlit
if 'manager' not in st.session_state:
    st.session_state.manager = GeoValidaManager()

render_dashboard(st.session_state.manager)