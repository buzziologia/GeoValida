# -*- coding: utf-8 -*-
import networkx as nx
import geopandas as gpd
import logging
from typing import List, Set
from utils.territorial_graph import TerritorialHierarchyGraph

class TerritorialValidator:
    # Ranking atualizado baseado nos nomes presentes em SEDE+regic
    # Menor valor = Maior influência
    REGIC_RANK = {
        'Metrópole Nacional': 1,
        'Metrópole': 2,
        'Capital Regional A': 3,
        'Capital Regional B': 4,
        'Capital Regional C': 5,
        'Centro Sub-Regional A': 6,
        'Centro Sub-Regional B': 7,
        'Centro de Zona A': 8,
        'Centro de Zona B': 9,
        'Centro Local': 10,
        'Sem Dados': 98,
        '6': 99 # Padrão caso não encontrado
    }
    
    def __init__(self, graph: TerritorialHierarchyGraph):
        self.graph = graph
        self.logger = logging.getLogger("TerritorialValidator")

    def get_regic_score(self, cd_mun: int) -> int:
        """Retorna o peso hierárquico usando as descrições carregadas no grafo."""
        level_desc = self.graph.mun_regic.get(int(cd_mun), '6')
        return self.REGIC_RANK.get(level_desc, 99)

    def get_shared_boundary_length(self, mun_id: int, target_utp_id: str, gdf: gpd.GeoDataFrame) -> float:
        """Calcula o comprimento da fronteira partilhada em metros."""
        if gdf is None or gdf.empty: 
            return 0.0
        
        # 1. Filtra a geometria do município de origem
        mun_rows = gdf[gdf['CD_MUN'] == mun_id]
        if mun_rows.empty: 
            return 0.0
        mun_geom = mun_rows.geometry.values[0]
        
        # 2. Filtra e funde as geometrias da UTP alvo (unary_union garante um objeto Geometry)
        target_rows = gdf[gdf['UTP_ID'] == str(target_utp_id)]
        if target_rows.empty: 
            return 0.0
        
        # unary_union transforma a GeoSeries em uma única Geometria (Poly ou MultiPoly)
        target_utp_geom = target_rows.unary_union
        
        # Validação de segurança: garante que ambos são objetos de geometria antes da interseção
        if mun_geom is None or target_utp_geom is None or target_utp_geom.is_empty:
            return 0.0
            
        # 3. Interseção das bordas (perímetro de contato)
        # mun_geom.boundary extrai apenas a linha do contorno
        shared = mun_geom.boundary.intersection(target_utp_geom)
        
        return shared.length
    
    def get_rm_of_utp(self, utp_id: str) -> str:
        utp_node = f"UTP_{utp_id}"
        if not self.graph.hierarchy.has_node(utp_node): return "NAO_ENCONTRADA"
        parents = list(self.graph.hierarchy.predecessors(utp_node))
        return parents[0] if parents else "SEM_RM"

    def is_change_allowed(self, mun_id: int, target_utp_id: str, gdf: gpd.GeoDataFrame) -> bool:
        """Verifica RM e Adjacência Geográfica."""
        # 1. Validação de RM
        current_utp = self.graph.get_municipality_utp(mun_id)
        rm_origin = self.get_rm_of_utp(current_utp)
        rm_dest = self.get_rm_of_utp(target_utp_id)
        
        if rm_origin != rm_dest:
            return False

        # 2. Validação de Adjacência (Novo)
        # Filtra a geometria do município que quer mudar
        mun_geom = gdf[gdf['CD_MUN'] == mun_id].geometry.values[0]
        
        # Filtra as geometrias da UTP de destino
        # Nota: Usamos o UTP_ID atualizado no GeoDataFrame
        target_geoms = gdf[gdf['UTP_ID'] == str(target_utp_id)].geometry
        
        if target_geoms.empty:
            return False

        # Verifica se toca. O buffer de 0.01 graus (~1km) ajuda em ilhas como Ilhabela
        return target_geoms.intersects(mun_geom.buffer(0.01)).any()

    def validate_utp_contiguity(self, utp_id: str, gdf_mun_utp: gpd.GeoDataFrame, sede_id: int) -> List[int]:
        """
        Usa BFS para encontrar municípios isolados (enclaves) dentro de uma UTP.
        Retorna uma lista de IDs de municípios que não conseguem chegar à SEDE.
        """
        if gdf_mun_utp.empty:
            return []

        # 1. Construir grafo de vizinhança física apenas para esta UTP
        G = nx.Graph()
        municipios_ids = gdf_mun_utp['CD_MUN'].tolist()
        G.add_nodes_from(municipios_ids)

        for i, row in gdf_mun_utp.iterrows():
            # Encontra vizinhos que tocam este município e pertencem à mesma UTP
            vizinhos = gdf_mun_utp[gdf_mun_utp.geometry.touches(row.geometry)]['CD_MUN'].tolist()
            for v in vizinhos:
                G.add_edge(row['CD_MUN'], v)

        # 2. Executar BFS a partir da SEDE
        if sede_id not in G:
            self.logger.error(f"Erro Contiguidade: SEDE {sede_id} não encontrada na UTP {utp_id}")
            return []

        alcancaveis = nx.node_connected_component(G, sede_id)
        isolados = [m for m in municipios_ids if m not in alcancaveis]

        if isolados:
            self.logger.warning(f"UTP {utp_id} possui {len(isolados)} municípios isolados.")
            
        return isolados

    def is_adjacent(self, mun_id: int, target_utp_id: str, gdf: gpd.GeoDataFrame) -> bool:
        """Verifica se o município toca geograficamente qualquer município da UTP destino."""
        mun_geom = gdf[gdf['CD_MUN'] == mun_id].geometry.values[0]
        
        # Filtra municípios que já pertencem à UTP de destino
        target_utp_geoms = gdf[gdf['UTP_ID'] == str(target_utp_id)].geometry
        
        if target_utp_geoms.empty:
            return False

        # Verifica se toca (com buffer de 1km para casos de ilhas/litoral)
        return target_utp_geoms.touches(mun_geom.buffer(0.01)).any()
    
    def is_adjacent_to_any_in_utp(self, mun_id: int, target_utp_id: str, gdf: gpd.GeoDataFrame) -> bool:
        """
        Verifica se o município toca QUALQUER município da UTP de destino.
        """
        if gdf is None or gdf.empty: return False

        # 1. Geometria do município unitário
        mun_row = gdf[gdf['CD_MUN'] == mun_id]
        if mun_row.empty: return False
        mun_geom = mun_row.geometry.values[0]

        # 2. Geometrias de TODOS os municípios da UTP alvo
        # Importante: filtramos no GDF pela UTP_ID que o mapa já sincronizou
        target_geoms = gdf[gdf['UTP_ID'] == str(target_utp_id)].geometry
        
        if target_geoms.empty: return False

        # 3. Verifica interseção com buffer (para Ilhabela e litorâneos)
        # O município não precisa tocar o destino principal, apenas ALGUÉM da UTP alvo
        return target_geoms.intersects(mun_geom.buffer(0.01)).any()
    
    def is_non_rm(self, utp_id: str) -> bool:
        """Verifica se a UTP pertence ao grupo SEM_RM."""
        rm_node = self.get_rm_of_utp(utp_id)
        return rm_node == "RM_SEM_RM"
    
    def is_non_rm_utp(self, utp_id: str) -> bool:
        """Verifica se a UTP pertence ao grupo genérico SEM_RM."""
        rm_node = self.get_rm_of_utp(utp_id)
        return rm_node == "RM_SEM_RM"

    def get_neighboring_utps(self, mun_id: int, gdf: gpd.GeoDataFrame) -> List[str]:
        """Retorna IDs de UTPs que fazem fronteira com o município."""
        if gdf is None or gdf.empty: return []
        
        mun_geom = gdf[gdf['CD_MUN'] == mun_id].geometry.values[0]
        # Buffer de 0.05 (~5km) para capturar vizinhança robusta (incluindo ilhas)
        neighbors = gdf[gdf.geometry.intersects(mun_geom.buffer(0.05))]
        
        return neighbors['UTP_ID'].dropna().unique().astype(str).tolist()