# src/config.py
from pathlib import Path
import logging

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "01_raw"
INTERIM_DIR = DATA_DIR / "02_intermediate"
MAPS_DIR = DATA_DIR / "04_maps"

FILES = {
    # Inputs (Coloque seus CSVs/Excels aqui)
    "utp_base": RAW_DIR / "UTP_FINAL.csv",
    "sede_regic": RAW_DIR / "SEDE+regic.csv",
    "matriz_pessoas": RAW_DIR / "person-matrix-data",
    "impedancias": RAW_DIR / "impedance" / "impedancias_filtradas_2h.csv",
    "shapefiles": RAW_DIR / "shapefiles",

    # Outputs
    "res_destino_principal": INTERIM_DIR / "res_fluxos.csv",
    "mapa_01": MAPS_DIR / "01_INICIAL.png",
    "mapa_05": MAPS_DIR / "05_FUNCIONAL.png",
    "mapa_final": MAPS_DIR / "FINAL_CONSOLIDADO.png"
}

# Criar pastas automaticamente se não existirem
for folder in [INTERIM_DIR, MAPS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)