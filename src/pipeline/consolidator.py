# src/pipeline/consolidator.py
import logging
import pandas as pd
import geopandas as gpd
from src.core.validator import TerritorialValidator

class UTPConsolidator:
    def __init__(self, graph, validator: TerritorialValidator):
        self.graph = graph
        self.validator = validator
        self.logger = logging.getLogger("GeoValida.Consolidator")

    def run_functional_merging(self, flow_df: pd.DataFrame) -> int:
        """Passo 5: Consolidação baseada em Fluxo de Viagens."""
        self.logger.info("Executando consolidação funcional...")
        # Implementa a lógica de percorrer UTPs unitárias e buscar destino principal
        # ... (seu código do Passo 5 atualizado)
        return total_changes

    def run_territorial_regic(self, gdf: gpd.GeoDataFrame, map_gen) -> int:
        """Passo 7: Limpeza de unitárias usando REGIC + Envolvência (Métrica)."""
        self.logger.info("Executando limpeza territorial via REGIC...")
        # Usa o CRS 5880 e get_shared_boundary_length para precisão métrica
        # ... (seu código do Passo 7 que corrigimos anteriormente)
        return total_changes