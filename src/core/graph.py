import networkx as nx
import pandas as pd
import geopandas as gpd
import logging
from typing import Dict, List, Optional, Union
from pathlib import Path

class TerritorialGraph:
    """
    Classe para gerenciar a hierarquia territorial brasileira e integração funcional.
    Estrutura: Brasil (Raiz) -> RMs (Nós) -> UTPs (Subnós) -> Municípios (Folhas).
    Integração: Municípios possuem arestas com pesos baseados em impedâncias.
    """

    def __init__(self):
        # Grafo Direcionado para Hierarquia (Pai -> Filho)
        self.hierarchy = nx.DiGraph()
        # Grafo Não-Direcionado para Impedâncias Funcionais (Distância/Tempo)
        self.functional = nx.Graph()
        
        # Armazenamento
        self.utp_seeds = {} # Armazena utp_id -> cd_mun (sede)
        self.mun_regic = {} # cd_mun -> regic_code (ex: '2B')
        
        # Inicializa a raiz
        self.root = "BRASIL"
        self.hierarchy.add_node(self.root, type='country', level=0)
        
        logging.info("Grafo Territorial inicializado.")

    def add_rm(self, rm_name: str):
        """Adiciona uma Região Metropolitana ao grafo."""
        node_id = f"RM_{rm_name}"
        if not self.hierarchy.has_node(node_id):
            self.hierarchy.add_node(node_id, type='rm', name=rm_name, level=1)
            self.hierarchy.add_edge(self.root, node_id)
        return node_id

    def add_utp(self, utp_id: Union[str, int], parent_id: str = "BRASIL"):
        """Adiciona uma UTP vinculada a uma RM ou diretamente ao Brasil."""
        node_id = f"UTP_{utp_id}"
        if not self.hierarchy.has_node(node_id):
            self.hierarchy.add_node(node_id, type='utp', utp_id=utp_id, level=2)
            self.hierarchy.add_edge(parent_id, node_id)
        return node_id

    def add_municipality(self, cd_mun: int, nm_mun: str, utp_id: Union[str, int]):
        """Adiciona um município vinculado a uma UTP."""
        mun_id = int(cd_mun)
        utp_node = f"UTP_{utp_id}"
        
        # Garante que a UTP existe
        if not self.hierarchy.has_node(utp_node):
            self.add_utp(utp_id)
            
        self.hierarchy.add_node(mun_id, type='municipality', name=nm_mun, level=3)
        self.hierarchy.add_edge(utp_node, mun_id)
        self.functional.add_node(mun_id, name=nm_mun)

    def move_municipality(self, cd_mun: int, target_utp_id: Union[str, int]):
        """Troca um município de UTP, removendo o vínculo anterior."""
        mun_id = int(cd_mun)
        target_utp_node = f"UTP_{target_utp_id}"
        
        if not self.hierarchy.has_node(mun_id):
            raise ValueError(f"Município {cd_mun} não existe no grafo.")
        
        # Remove arestas de hierarquia atuais (um mun só tem um pai UTP)
        old_parents = [p for p in self.hierarchy.predecessors(mun_id) 
                       if self.hierarchy.nodes[p]['type'] == 'utp']
        for p in old_parents:
            self.hierarchy.remove_edge(p, mun_id)
            
        # Adiciona à nova UTP
        if not self.hierarchy.has_node(target_utp_node):
            self.add_utp(target_utp_id)
        self.hierarchy.add_edge(target_utp_node, mun_id)
        
        logging.info(f"Município {cd_mun} movido para {target_utp_node}.")

    def add_impedance(self, origin: int, destination: int, weight: float):
        """Adiciona peso funcional (impedância) entre dois municípios."""
        if self.functional.has_node(origin) and self.functional.has_node(destination):
            self.functional.add_edge(origin, destination, weight=weight)

    def load_from_dataframe(self, df_base: pd.DataFrame, df_regic: pd.DataFrame):
        """
        Popula o grafo: df_regic define as Sedes/REGIC e df_base define o Território.
        A ID da UTP é estritamente a coluna 'UTPs_PAN_3'.
        """
        logging.info("Vinculando Sedes e REGIC pela coluna UTPs_PAN_3...")
        
        # 1. Carrega Sedes e REGIC do arquivo externo
        for _, row in df_regic.iterrows():
            cd_mun = int(row['CD_MUN'])
            utp_id = str(row['UTPs_PAN_3'])
            regic_desc = str(row['REGIC'])
            
            # Define o município como SEDE e guarda o seu nível de influência
            self.utp_seeds[utp_id] = cd_mun
            self.mun_regic[cd_mun] = regic_desc
            
        # 2. Constrói a hierarquia baseada no território principal
        for _, row in df_base.iterrows():
            cd_mun = int(row['CD_MUN'])
            nm_mun = row['NM_MUN']
            utp_id = str(row['UTPs_PAN_3'])
            
            # Identifica Região Metropolitana (NM_CONCU)
            rm_name = str(row['NM_CONCU']) if pd.notna(row['NM_CONCU']) else "SEM_RM"
            
            # Criação dos nós no grafo (RM -> UTP -> Município)
            rm_node = f"RM_{rm_name}"
            if not self.hierarchy.has_node(rm_node):
                self.hierarchy.add_node(rm_node, type='rm', name=rm_name)
                self.hierarchy.add_edge(self.root, rm_node)

            utp_node = f"UTP_{utp_id}"
            if not self.hierarchy.has_node(utp_node):
                self.hierarchy.add_node(utp_node, type='utp', utp_id=utp_id)
                self.hierarchy.add_edge(rm_node, utp_node)
            
            self.hierarchy.add_node(cd_mun, type='municipality', name=nm_mun)
            self.hierarchy.add_edge(utp_node, cd_mun)

        logging.info("Grafo Territorial populado com sucesso.")

    def get_municipality_utp(self, cd_mun: int) -> str:
        """Retorna o ID da UTP de um município."""
        if not self.hierarchy.has_node(cd_mun):
            return "NAO_ENCONTRADO"
        
        # O pai do município é sempre o nó da UTP
        parents = list(self.hierarchy.predecessors(cd_mun))
        for p in parents:
            if str(p).startswith("UTP_"):
                return str(p).replace("UTP_", "")
        return "SEM_UTP"

    def export_to_csv(self, path: Path):
        """Exporta a estrutura de hierarquia para um CSV legível."""
        rows = []
        for u, v, data in self.hierarchy.edges(data=True):
            rows.append({
                "parent": u,
                "child": v,
                "parent_type": self.hierarchy.nodes[u]['type'],
                "child_type": self.hierarchy.nodes[v]['type']
            })
        pd.DataFrame(rows).to_csv(path, index=False, sep=';')
        logging.info(f"Hierarquia exportada para {path}")

    
    def get_unitary_utps(self) -> List[str]:
        """
        Identifica e retorna uma lista com os IDs de todas as UTPs 
        que possuem apenas um único município vinculado.
        """
        unitary_utps = []
        
        # 1. Filtra todos os nós que são do tipo 'utp'
        utp_nodes = [n for n, d in self.hierarchy.nodes(data=True) if d.get('type') == 'utp']
        
        for node in utp_nodes:
            # 2. No NetworkX, os municípios são sucessores (filhos) do nó UTP
            successors = list(self.hierarchy.successors(node))
            
            # 3. Se houver exatamente um sucessor, é uma UTP unitária
            if len(successors) == 1:
                # Remove o prefixo 'UTP_' para retornar apenas o ID limpo
                utp_id = str(node).replace("UTP_", "")
                unitary_utps.append(utp_id)
                
        return unitary_utps

    def compute_graph_coloring(self, gdf: gpd.GeoDataFrame) -> Dict[int, int]:
        """
        Computa coloração de grafo otimizada por UTPs e não por municípios.
        Todos os municípios da mesma UTP terão a mesma cor.
        UTPs vizinhas terão cores diferentes.
        """
        if gdf.empty:
            return {}

        logging.info("Iniciando coloração baseada em UTPs...")
        
        # 0. Verificar se UTP_ID existe e limpar NAs
        if 'UTP_ID' not in gdf.columns:
            logging.error("Coluna 'UTP_ID' não encontrada no GeoDataFrame")
            return {}
        
        # Remove linhas com UTP_ID faltando
        gdf_clean = gdf.dropna(subset=['UTP_ID']).copy()
        if gdf_clean.empty:
            logging.error("Nenhum município com UTP_ID válido")
            return {}
        
        # 1. Agrupar (Dissolver) geometrias por UTP para criar polígonos das UTPs
        #    Mantém apenas a geometria para performance
        try:
            gdf_utps = gdf_clean[['UTP_ID', 'geometry']].copy()
            gdf_utps = gdf_utps.dissolve(by='UTP_ID', aggfunc='first')
            gdf_utps = gdf_utps.reset_index()  # Converte UTP_ID de índice para coluna
            logging.info(f"Dissolve concluído: {len(gdf_utps)} UTPs criadas")
        except Exception as e:
            logging.error(f"Erro ao dissolver UTPs: {e}")
            logging.error(f"Colunas do GDF: {gdf_clean.columns.tolist()}")
            return {}

        # 2. Criar grafo de adjacência das UTPs
        adjacency_graph = nx.Graph()
        # Adiciona todas as UTPs como nós (agora está em coluna 'UTP_ID')
        adjacency_graph.add_nodes_from(gdf_utps['UTP_ID'].unique())

        # 3. Usar spatial join para encontrar UTPs vizinhas
        #    Usamos gdf_utps contra ele mesmo
        try:
            neighbors = gpd.sjoin(gdf_utps, gdf_utps, predicate='touches', how='inner')
            
            # Filtra auto-relacionamentos (UTP tocando ela mesma)
            neighbors = neighbors[neighbors['UTP_ID_left'] != neighbors['UTP_ID_right']]
            
            # 4. Adicionar arestas ao grafo
            edges = zip(neighbors['UTP_ID_left'], neighbors['UTP_ID_right'])
            adjacency_graph.add_edges_from(edges)
            
        except Exception as e:
            logging.error(f"Erro ao calcular adjacência de UTPs: {e}")
            # Fallback: colorir aleatoriamente ou sequencialmente se falhar
            return {}

        # 5. Algoritmo Greedy de Coloração (Strategy: DSATUR)
        utp_coloring = nx.coloring.greedy_color(adjacency_graph, strategy='DSATUR')
        
        # 6. Mapear a cor da UTP de volta para cada município
        #    Resultado esperado: cd_mun -> color_index
        final_coloring = {}
        
        # Cria um lookup UTP_ID -> Cor
        # Itera sobre o GDF original (LIMPO) para atribuir a cor
        for _, row in gdf_clean.iterrows():
            cd_mun = row['CD_MUN']
            utp_id = row['UTP_ID']
            
            # Se a UTP foi colorida, atribui a cor. Se não (casos isolados?), usa cor 0.
            color = utp_coloring.get(utp_id, 0)
            final_coloring[cd_mun] = color
            
        logging.info(f"Coloração de UTPs concluída: {len(utp_coloring)} UTPs coloridas mapeadas para municípios.")
        return final_coloring

