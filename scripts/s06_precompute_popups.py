
"""
Script to pre-compute flow popups for all municipalities.
This avoids heavy calculation during dashboard startup.
"""
import sys
import pandas as pd
import json
import logging
from pathlib import Path
from tqdm import tqdm

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from src.config import setup_logging
from src.utils import DataLoader
from src.interface.flow_utils import get_top_destinations_for_municipality, format_flow_popup_html, get_municipality_total_flow

logger = logging.getLogger(__name__)

def load_impedance_data():
    """Loads impedance data for travel time calculations."""
    try:
        impedance_path = PROJECT_ROOT / "data" / "01_raw" / "impedance" / "impedancias_filtradas_2h.csv"
        if impedance_path.exists():
            df_impedance = pd.read_csv(impedance_path, sep=';', encoding='latin-1')
            df_impedance = df_impedance.dropna(axis=1, how='all')
            df_impedance = df_impedance.rename(columns={
                'COD_IBGE_ORIGEM_1': 'origem_6',
                'COD_IBGE_DESTINO_1': 'destino_6',
                'Tempo': 'tempo_horas'
            })
            # Convert tempo_horas to float
            df_impedance['tempo_horas'] = (
                df_impedance['tempo_horas'].astype(str).str.replace(',', '.').astype(float)
            )
            # Ensure 6-digit keys are int
            df_impedance['origem_6'] = pd.to_numeric(df_impedance['origem_6'], errors='coerce').fillna(0).astype(int)
            df_impedance['destino_6'] = pd.to_numeric(df_impedance['destino_6'], errors='coerce').fillna(0).astype(int)
            logger.info(f"Loaded {len(df_impedance)} impedance pairs for popup times")
            return df_impedance
        else:
            logger.warning(f"Impedance file not found: {impedance_path}")
            return None
    except Exception as e:
        logger.warning(f"Could not load impedance data for popups: {e}")
        return None

def main():
    logger.info("Starting Flow Popups Pre-computation...")
    
    # 1. Load Data
    data_loader = DataLoader() # Initialize DataLoader
    df_municipios = data_loader.get_municipios_dataframe() # Load dataframe
    
    if df_municipios.empty:
        logger.error("Failed to load municipality data.")
        return 1
        
    df_impedance = load_impedance_data()
    
    # 2. Setup lookup dictionary (similar to map_flow_render.py)
    df_lookup = df_municipios.set_index('cd_mun') if 'cd_mun' in df_municipios.columns else pd.DataFrame()
    
    # 3. Create Popups
    popups = {}
    
    # Prepare data for lookup efficiency
    # Convert dataframe to a list of dicts for iteration, but keep df_lookup for fast random access
    
    logger.info(f"Computing popups for {len(df_municipios)} municipalities...")
    
    count = 0
    for idx, row in tqdm(df_municipios.iterrows(), total=len(df_municipios), desc="Computing Popups"):
        try:
            cd_mun_val = row.get('CD_MUN') if 'CD_MUN' in row else row.get('cd_mun')
            if not cd_mun_val: continue
            
            cd_mun = str(cd_mun_val)
            nm_mun = row.get('NM_MUN', row.get('nm_mun', 'Desconhecido'))
            utp_id = str(row.get('utp_id', ''))
            
            # Lookup detailed data (nested dicts/lists for modals)
            mun_data = {}
            if cd_mun in df_lookup.index:
                entry = df_lookup.loc[cd_mun]
                if isinstance(entry, pd.DataFrame):
                    entry = entry.iloc[0]
                mun_data = entry.to_dict()
                mun_data['cd_mun'] = cd_mun # Ensure ID is present
                # Preserve modal_matriz
                if 'modal_matriz' in entry:
                    mun_data['modal_matriz'] = entry['modal_matriz']
            else:
                 # Fallback to current row data converted to dict
                 mun_data = row.to_dict()
            
            # Calculate top destinations
            top_destinations = get_top_destinations_for_municipality(
                mun_data, df_municipios, top_n=5, df_impedance=df_impedance
            )
            
            # Extract fields
            regiao_metropolitana = row.get('regiao_metropolitana', mun_data.get('regiao_metropolitana', '-'))
            regic = row.get('regic', mun_data.get('regic', '-'))
            populacao = row.get('populacao_2022', mun_data.get('populacao_2022', 0))
            uf = row.get('uf', mun_data.get('uf', ''))
            
            total_viagens = get_municipality_total_flow(mun_data)
            
            # Generate HTML
            html = format_flow_popup_html(
                nm_mun=nm_mun, 
                cd_mun=cd_mun, 
                utp_id=utp_id, 
                top_destinations=top_destinations,
                regiao_metropolitana=regiao_metropolitana,
                regic=regic,
                populacao=populacao,
                total_viagens=total_viagens,
                uf=uf
            )
            
            popups[cd_mun] = html
            count += 1
            
        except Exception as e:
            logger.warning(f"Error computing popup for {row.get('nm_mun', 'unknown')}: {e}")
            continue

    # 4. Save to JSON
    output_dir = PROJECT_ROOT / "data" / "04_maps"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "flow_popups_optimized.json"
    
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(popups, f, ensure_ascii=False)
        logger.info(f"✅ Saved {count} popups to {output_path}")
        return 0
    except Exception as e:
        logger.error(f"❌ Failed to save popups: {e}")
        return 1

if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
