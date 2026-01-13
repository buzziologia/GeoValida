import logging
import pandas as pd
from pathlib import Path

# Importações modulares do novo diretório src/
from src.config import FILES, setup_logging
from src.core.graph import TerritorialGraph
from src.core.validator import TerritorialValidator
from src.pipeline.analyzer import ODAnalyzer
from src.pipeline.consolidator import UTPConsolidator
from src.pipeline.mapper import UTPMapGenerator

class GeoValidaManager:
    """
    Orquestrador Principal do GeoValida.
    Gere o estado do Grafo, Análise de Fluxos e Geração de Mapas.
    """
    def __init__(self):
        # Inicializa o Logger centralizado
        setup_logging()
        self.logger = logging.getLogger("GeoValida")
        
        # Componentes Core
        self.graph = TerritorialGraph()
        self.validator = TerritorialValidator(self.graph)
        
        # Componentes de Pipeline
        self.analyzer = ODAnalyzer()
        self.map_generator = UTPMapGenerator(self.graph)
        self.consolidator = UTPConsolidator(self.graph, self.validator)

    def step_0_initialize_data(self):
        """Carrega as bases de dados e sincroniza o Grafo."""
        self.logger.info("Etapa 0: Carregando Bases de Dados...")
        try:
            # Leitura robusta (Lida com acentuação e erros de aspas)
            read_params = {'sep': ',', 'encoding': 'latin1', 'on_bad_lines': 'skip'}
            
            df_utp = pd.read_csv(FILES['utp_base'], **read_params)
            df_regic = pd.read_csv(FILES['sede_regic'], **read_params)
            
            # Popula o Grafo (Com proteção contra o erro 'true' da linha 4833)
            self.graph.load_from_dataframe(df_utp, df_regic)
            
            # Inicializa o GDF de municípios para o Mapa
            self.map_generator.load_shapefiles()
            
            self.logger.info(f"Dados carregados. Grafo: {len(self.graph.hierarchy.nodes)} nós.")
            return True
        except Exception as e:
            self.logger.error(f"Erro na Inicialização: {e}")
            return False

    def step_1_generate_initial_map(self):
        """Gera o mapa da situação atual das UTPs."""
        self.logger.info("Etapa 1: Gerando Mapa Inicial...")
        (self.map_generator
            .sync_with_graph(self.graph)
            .save_map(FILES['mapa_01'], title="Situação Inicial das UTPs"))

    def step_2_analyze_flows(self):
        """Analisa a Matriz OD para encontrar dependências funcionais."""
        self.logger.info("Etapa 2: Analisando Fluxos de Viagens...")
        self.analyzer.run_full_analysis()
        return self.analyzer.full_flow_df

    def step_5_consolidate_functional(self):
        """Une UTPs baseadas estritamente em Fluxos (Passo 5)."""
        self.logger.info("Etapa 5: Consolidação Funcional (Fluxos)...")
        changes = self.consolidator.run_functional_merging(self.analyzer.full_flow_df)
        
        # Gera o mapa intermédio
        (self.map_generator
            .sync_with_graph(self.graph)
            .save_map(FILES['mapa_05'], title="Pós-Consolidação Funcional (Fluxos)"))
        
        return changes

    def step_7_territorial_cleanup(self):
        """Resolve UTPs unitárias usando REGIC + Adjacência (Passo 7)."""
        self.logger.info("Etapa 7: Limpeza Territorial Final (REGIC + Geografia)...")
        
        # Executa a lógica corrigida (EPSG:5880 + Boundary Length)
        changes = self.consolidator.run_territorial_regic(
            self.map_generator.gdf_complete, 
            self.map_generator
        )
        
        # Gera o mapa final absoluto
        (self.map_generator
            .sync_with_graph(self.graph)
            .save_map(FILES['mapa_final'], title="Resultado Final: Mapa Estruturado"))
        
        return changes

# --- Bloco de Execução via Terminal ---
if __name__ == "__main__":
    app = GeoValidaManager()
    
    if app.step_0_initialize_data():
        app.step_1_generate_initial_map()
        app.step_2_analyze_flows()
        
        c5 = app.step_5_consolidate_functional()
        print(f"Passo 5: {c5} uniões realizadas.")
        
        c7 = app.step_7_territorial_cleanup()
        print(f"Passo 7: {c7} uniões realizadas.")
        
        print("\nPipeline GeoValida finalizado com sucesso!")