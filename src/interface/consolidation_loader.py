# src/interface/consolidation_loader.py
"""
Loader de Consolidações - Sistema de Cache
Permite executar a consolidação uma vez e reutilizar o resultado
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import pandas as pd


class ConsolidationLoader:
    """Gerencia o carregamento e cache de consolidações."""
    
    def __init__(self):
        self.result_path = Path(__file__).parent.parent.parent / "data" / "consolidation_result.json"
        self.log_path = Path(__file__).parent.parent.parent / "data" / "consolidation_log.json"
        self.result = self._load_result()
    
    def _load_result(self) -> Dict:
        """Carrega o arquivo de resultado de consolidação."""
        if not self.result_path.exists():
            return {
                "version": "1.0",
                "status": "not_executed",
                "timestamp_created": None,
                "timestamp_last_updated": None,
                "total_consolidations": 0,
                "utps_mapping": {},  # {source_utp: target_utp}
                "consolidations": []  # Lista de detalhes
            }
        
        try:
            with open(self.result_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Erro ao carregar resultado: {e}")
            return self._default_result()
    
    def _default_result(self) -> Dict:
        """Retorna estrutura padrão."""
        return {
            "version": "1.0",
            "status": "not_executed",
            "timestamp_created": None,
            "timestamp_last_updated": None,
            "total_consolidations": 0,
            "utps_mapping": {},
            "consolidations": []
        }
    
    def save_result(self):
        """Salva o resultado de consolidação."""
        try:
            self.result_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.result_path, 'w', encoding='utf-8') as f:
                json.dump(self.result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Erro ao salvar resultado: {e}")
    
    def is_executed(self) -> bool:
        """Verifica se a consolidação já foi executada (independente do número de mudanças)."""
        return self.result["status"] == "executed"
    
    def get_utps_mapping(self) -> Dict:
        """Retorna o mapeamento de UTPs (source -> target)."""
        return self.result["utps_mapping"]
    
    def get_consolidations(self) -> List[Dict]:
        """Retorna a lista de consolidações."""
        return self.result["consolidations"]
    
    def update_from_log(self, log_data: Dict):
        """Atualiza o resultado a partir do log de consolidação."""
        consolidations = log_data.get("consolidations", [])
        
        # Criar mapeamento
        mapping = {}
        for cons in consolidations:
            mapping[cons["source_utp"]] = cons["target_utp"]
        
        self.result = {
            "version": "1.0",
            "status": "executed",
            "timestamp_created": self.result["timestamp_created"] or datetime.now().isoformat(),
            "timestamp_last_updated": datetime.now().isoformat(),
            "total_consolidations": len(consolidations),
            "utps_mapping": mapping,
            "consolidations": consolidations
        }
        
        self.save_result()
    
    def apply_consolidations_to_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica as consolidações a um dataframe.
        
        Args:
            df: DataFrame com coluna 'utp_id'
        
        Returns:
            DataFrame com UTPs consolidadas
        """
        if not self.is_executed():
            return df.copy()
        
        df_consolidated = df.copy()
        mapping = self.get_utps_mapping()
        
        # Aplicar mapeamento
        df_consolidated['utp_id'] = df_consolidated['utp_id'].map(
            lambda x: mapping.get(x, x)
        )
        
        return df_consolidated
    
    def get_summary(self) -> Dict:
        """Retorna um resumo da consolidação."""
        mapping = self.result["utps_mapping"]
        consolidations = self.result["consolidations"]
        
        reasons = {}
        for cons in consolidations:
            reason = cons.get("reason", "Desconhecido")
            reasons[reason] = reasons.get(reason, 0) + 1
        
        return {
            "status": self.result["status"],
            "executed": self.is_executed(),
            "timestamp": self.result["timestamp_last_updated"],
            "total_consolidations": self.result["total_consolidations"],
            "unique_sources": len(mapping),
            "unique_targets": len(set(mapping.values())),
            "reasons": reasons
        }
    
    def get_statistics(self, df_initial: pd.DataFrame, df_consolidated: pd.DataFrame) -> Dict:
        """Calcula estatísticas de consolidação."""
        return {
            "utps_before": df_initial['utp_id'].nunique(),
            "utps_after": df_consolidated['utp_id'].nunique(),
            "reduction": df_initial['utp_id'].nunique() - df_consolidated['utp_id'].nunique(),
            "reduction_percentage": (
                (df_initial['utp_id'].nunique() - df_consolidated['utp_id'].nunique()) / 
                df_initial['utp_id'].nunique() * 100
            )
        }
    
    def export_as_dataframe(self) -> pd.DataFrame:
        """Exporta as consolidações como DataFrame."""
        consolidations = self.result["consolidations"]
        
        if not consolidations:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                "ID": i + 1,
                "UTP Origem": c["source_utp"],
                "UTP Destino": c["target_utp"],
                "Motivo": c.get("reason", "N/A"),
                "Data": c["timestamp"][:10],
                "Hora": c["timestamp"][11:19]
            }
            for i, c in enumerate(consolidations)
        ])
    
    def clear(self):
        """Limpa o resultado de consolidação."""
        self.result = self._default_result()
        self.save_result()
