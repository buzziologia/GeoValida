import json

with open('initialization.json', 'r', encoding='utf-8') as f:
    j = json.load(f)

print(f"Total de Municipios: {len(j['municipios'])}")
print(f"Total de UTPs: {len(j['utps'])}")
print(f"Metadata: {j['metadata']}\n")

# Verificar campos
muns_com_uf = sum(1 for m in j['municipios'] if m.get('uf'))
muns_com_pop = sum(1 for m in j['municipios'] if m.get('populacao_2022', 0) > 0)
muns_com_imp_2h = sum(1 for m in j['municipios'] if m.get('impedancia_2h_filtrada'))

print(f"Municipios com UF: {muns_com_uf}")
print(f"Municipios com População > 0: {muns_com_pop}")
print(f"Municipios com Impedancia 2h: {muns_com_imp_2h}\n")

# Amostra
m = j['municipios'][0]
print("=== AMOSTRA DO PRIMEIRO MUNICIPIO ===")
print(f"Nome: {m.get('nm_mun')}")
print(f"CD_MUN: {m.get('cd_mun')}")
print(f"UF: {m.get('uf')}")
print(f"Populacao 2022: {m.get('populacao_2022')}")
print(f"Impedancia 2h: {m.get('impedancia_2h_filtrada')}")
print(f"Modais: {list(m.get('modais', {}).keys())}")
print(f"Tem modal_matriz: {'modal_matriz' in m}")

# Verificar arquivo
import os
size_mb = os.path.getsize('initialization.json') / (1024*1024)
print(f"\nTamanho do arquivo: {size_mb:.2f} MB")
