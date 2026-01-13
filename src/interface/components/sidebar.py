# src/interface/components/sidebar.py
import streamlit as st

def render_sidebar(manager):
    st.sidebar.image("https://labtrans.ufsc.br/logo.png", width=200) # Exemplo
    st.sidebar.title("GeoValida Control")
    
    step = st.sidebar.radio(
        "Selecione a Etapa:",
        ["0. Carga de Dados", "1. Mapa Inicial", "2. Análise de Fluxos", "5. Consolidação Funcional", "7. Limpeza REGIC"]
    )
    
    st.sidebar.divider()
    if st.sidebar.button("🗑️ Limpar Cache/Reset"):
        st.cache_resource.clear()
        st.rerun()
        
    return step