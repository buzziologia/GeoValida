# src/interface/dashboard.py
import streamlit as st
from src.interface.components import sidebar, metrics, map_viewer

def render_dashboard(manager):
    """Função principal que desenha a interface do GeoValida."""
    
    # 1. Renderiza a Sidebar e obtém a etapa selecionada
    selected_step = sidebar.render_sidebar(manager)
    
    # 2. Mostra métricas gerais no topo (Municípios, UTPs, etc.)
    metrics.render_top_metrics(manager)

    # 3. Organização por abas para não poluir o ecrã
    tab_proc, tab_viz = st.tabs(["⚙️ Processamento", "🗺️ Visualização Espacial"])

    with tab_proc:
        if selected_step == "0. Carga de Dados":
            st.info("Aguardando carregamento das bases de dados...")
            if st.button("Carregar Dados"):
                if manager.step_0_initialize_data():
                    st.success("Dados carregados com sucesso!")
        
        elif selected_step == "2. Análise de Fluxos":
            st.subheader("Resultados da Matriz OD")
            df_flows = manager.step_2_analyze_flows()
            st.dataframe(df_flows, use_container_width=True)

        elif selected_step == "7. Limpeza REGIC":
            st.subheader("Consolidação Final (REGIC + Adjacência)")
            if st.button("Executar Limpeza"):
                changes = manager.step_7_territorial_cleanup()
                st.write(f"✅ {changes} municípios consolidados.")

    with tab_viz:
        map_viewer.render_maps(selected_step)