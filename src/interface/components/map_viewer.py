# src/interface/components/map_viewer.py
import streamlit as st
import folium
import geopandas as gpd
import json
import logging
from typing import Dict, Any

# Paleta de cores oficial Padrão Digital de Governo (Gov.br)
GOVBR_COLORS = [
    "#1351B4", "#168821", "#E52207", "#FFCD07", "#155BCB", 
    "#00A871", "#0076D6", "#0C326F", "#5AB9B3", "#8289FF", 
    "#AD79E9", "#BE32D0"
]

def create_interactive_map(gdf: gpd.GeoDataFrame, 
                           coloring: Dict[int, int],
                           seats: Dict[Any, int]) -> folium.Map:
    """
    Cria um mapa interativo utilizando folium puro com tooltips e popups.
    Simplifica geometrias para reduzir tamanho do HTML.
    """
    
    # 1. Inicializar o mapa (centralizado no Brasil)
    m = folium.Map(
        location=[-15.78, -47.93], 
        zoom_start=4,
        tiles="CartoDB positron"
    )
    
    # Conjunto de IDs de municípios que são sedes
    seat_ids = set(seats.values())
    
    # 2. Simplificar geometrias com preservação de topologia - tolerance de 0.003 graus (~300m)
    gdf_simplified = gdf.copy()
    # Usar preserve_topology=True para evitar deformações e self-intersections
    gdf_simplified['geometry'] = gdf_simplified.geometry.simplify(tolerance=0.003, preserve_topology=True)
    
    # 3. Iterador pelas geometrias do GeoDataFrame
    for idx, row in gdf_simplified.iterrows():
        cd_mun = row.get('CD_MUN')
        nm_mun = row.get('NM_MUN', 'Sem Nome')
        utp_id = row.get('UTP_ID', 'N/A')
        geometry = row.geometry
        
        # 4. Determinar cores e estilos baseado na coloração do grafo
        color_idx = coloring.get(cd_mun, 0) % len(GOVBR_COLORS)
        fill_color = GOVBR_COLORS[color_idx]
        
        is_seed = cd_mun in seat_ids
        border_color = "#000000" if is_seed else "#808080"  # Preto para sedes, cinza para membros
        border_weight = 2.5 if is_seed else 1.5
        
        # 5. Criar conteúdo do popup
        popup_text = f"""
        <div style="font-family: Arial, sans-serif; width: 250px;">
            <b style="color: #1351B4; font-size: 14px;">{nm_mun}</b><br>
            <hr style="margin: 5px 0; border: none; border-top: 1px solid #ccc;">
            <table style="width: 100%; font-size: 12px;">
                <tr><td><b>Código IBGE:</b></td><td>{cd_mun}</td></tr>
                <tr><td><b>ID UTP:</b></td><td>{utp_id}</td></tr>
                <tr><td><b>Status:</b></td><td>{'<span style="color: #168821;">🔵 Sede</span>' if is_seed else 'Membro'}</td></tr>
            </table>
        </div>
        """
        
        # 6. Criar tooltip (ao passar o mouse)
        tooltip_text = f"{nm_mun} (CD: {cd_mun})"
        
        # 7. Adicionar a geometria ao mapa como GeoJson com tooltip
        if geometry.geom_type == 'Polygon':
            # Swap coordinates: shapely (lon, lat) -> folium (lat, lon)
            coords = [(y, x) for x, y in geometry.exterior.coords]
            folium.Polygon(
                locations=coords,
                color=border_color,
                weight=border_weight,
                fillColor=fill_color,
                fillOpacity=0.8,
                popup=folium.Popup(popup_text, max_width=300),
                tooltip=folium.Tooltip(tooltip_text, sticky=False)
            ).add_to(m)
        elif geometry.geom_type == 'MultiPolygon':
            for part in geometry.geoms:
                # Swap coordinates: shapely (lon, lat) -> folium (lat, lon)
                coords = [(y, x) for x, y in part.exterior.coords]
                folium.Polygon(
                    locations=coords,
                    color=border_color,
                    weight=border_weight,
                    fillColor=fill_color,
                    fillOpacity=0.8,
                    popup=folium.Popup(popup_text, max_width=300),
                    tooltip=folium.Tooltip(tooltip_text, sticky=False)
                ).add_to(m)
    
    # 8. Adicionar Legenda
    legend_html = """
    <div style="position: fixed; 
                bottom: 50px; right: 50px; width: 240px; height: auto;
                background-color: white; border: 1px solid #DDDDDD; border-radius: 6px;
                z-index: 9999; font-size: 12px; padding: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="font-weight: 700; color: #1351B4; font-size: 13px; margin-bottom: 10px;">Legenda</div>
        <div style="margin-bottom: 8px;">
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="width: 16px; height: 16px; background-color: #1351B4; border: 2px solid #000; border-radius: 2px; margin-right: 8px;"></div>
                <span>Sede da UTP</span>
            </div>
            <div style="font-size: 11px; color: #666; margin-left: 24px;">Contorno preto destacado</div>
        </div>
        <div>
            <div style="display: flex; align-items: center; margin-bottom: 6px;">
                <div style="width: 16px; height: 16px; background-color: #E52207; border: 2px solid #808080; border-radius: 2px; margin-right: 8px;"></div>
                <span>Município Membro</span>
            </div>
            <div style="font-size: 11px; color: #666; margin-left: 24px;">Contorno cinza</div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

def render_maps(selected_step: str, manager=None):
    """Renderiza os mapas no Streamlit utilizando folium puro."""
    if manager is None or manager.gdf is None or manager.gdf.empty:
        st.warning("Dados não carregados para visualização.", icon="⚠️")
        return

    try:
        with st.spinner("A processar mapa interativo..."):
            # 1. Sincronizar dados do Grafo com o GeoDataFrame
            manager.map_generator.sync_with_graph(manager.graph)
            
            # 2. Garantir projeção WGS84
            gdf_map = manager.map_generator.gdf_complete.copy()
            if gdf_map.crs != "EPSG:4326":
                gdf_map = gdf_map.to_crs(epsg=4326)

            # 3. Calcular coloração de grafo
            coloring = manager.graph.compute_graph_coloring(gdf_map)
            seats = manager.graph.utp_seeds

            # 4. Criar o mapa folium
            m = create_interactive_map(gdf_map, coloring, seats)

            # 5. Renderizar no Streamlit usando st_folium ou components.v1.html
            from streamlit.components.v1 import html
            
            # Salvar mapa em HTML e renderizar
            map_html = m._repr_html_()
            html(map_html, height=700)
            
            st.caption(f"Visualização: {selected_step} | Total: {len(gdf_map)} municípios | Cores usadas: {len(set(coloring.values()))}")

    except Exception as e:
        st.error(f"Erro na renderização do mapa: {str(e)}")
        logging.error(f"Erro no map_viewer: {e}", exc_info=True)


def render_maps_filtered(selected_step: str, manager, gdf_filtered: gpd.GeoDataFrame, 
                         coloring: Dict[int, int], seats: Dict[Any, int]):
    """Renderiza o mapa filtrado no Streamlit."""
    if gdf_filtered is None or gdf_filtered.empty:
        st.warning("Nenhum dado para visualizar com os filtros atuais.")
        return

    try:
        # Criar o mapa folium
        m = create_interactive_map(gdf_filtered, coloring, seats)

        # Renderizar no Streamlit
        from streamlit.components.v1 import html
        map_html = m._repr_html_()
        html(map_html, height=700)
        
        st.caption(f"{selected_step} | Total: {len(gdf_filtered)} municípios")

    except Exception as e:
        st.error(f"Erro na renderização do mapa: {str(e)}")
        logging.error(f"Erro no map_viewer: {e}", exc_info=True)