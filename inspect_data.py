#!/usr/bin/env python3
import pandas as pd
from pathlib import Path

# Verificar população
print('=== POPULACAO 2022 ===')
try:
    files = list(Path('data/01_raw').glob('*POP*.xlsx'))
    if files:
        df_pop = pd.read_excel(files[0])
        print(f'File: {files[0].name}')
        print(f'Columns: {list(df_pop.columns)}')
        print(f'Shape: {df_pop.shape}')
        print(df_pop.head(2))
    else:
        print("Arquivo de população não encontrado")
except Exception as e:
    print(f"Erro: {e}")

# Verificar modal completo
print('\n=== MODAL - Rodoviaria Coletiva ===')
try:
    df_modal = pd.read_csv('data/01_raw/person-matrix-data/base_dados_rodoviaria_coletiva_2023.csv', sep=',', nrows=5)
    print(f'Columns: {list(df_modal.columns)}')
    print(f'Shape: {df_modal.shape}')
    print(df_modal.head(3).to_string())
except Exception as e:
    print(f"Erro: {e}")

# Verificar impedância
print('\n=== IMPEDANCIA 06h ===')
try:
    df_imp = pd.read_csv('data/01_raw/impedance/impedancias_06h_18_08_22.csv', sep=';', encoding='utf-8-sig', nrows=5)
    print(f'Columns: {list(df_imp.columns)}')
    print(f'Shape: {df_imp.shape}')
    print(df_imp.head(3).to_string())
except Exception as e:
    print(f"Erro: {e}")

# Verificar impedância 2h filtrada
print('\n=== IMPEDANCIA 2h Filtrada ===')
try:
    df_imp2 = pd.read_csv('data/01_raw/impedance/impedancias_filtradas_2h.csv', sep=';', encoding='utf-8-sig', nrows=5)
    print(f'Columns: {list(df_imp2.columns)}')
    print(f'Shape: {df_imp2.shape}')
    print(df_imp2.head(3).to_string())
except Exception as e:
    print(f"Erro: {e}")
