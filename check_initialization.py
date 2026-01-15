#!/usr/bin/env python3
import json

with open('initialization.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('=== ESTRUTURA DO JSON ===')
print(f'Total de municípios: {len(data["municipios"])}')
print(f'Total de UTPs: {len(data["utps"])}')
print(f'Total de dados de origem-destino por modal: {sum(1 for m in data["municipios"] if m["modal_matriz"])}')

print('\n=== EXEMPLO DE MUNICÍPIO COM DADOS ===')
for mun in data['municipios']:
    if mun['modal_matriz'] and mun['populacao_2022'] > 0:
        print(f'CD_MUN: {mun["cd_mun"]}')
        print(f'Nome: {mun["nm_mun"]}')
        print(f'UTP: {mun["utp_id"]}')
        print(f'Sede UTP: {mun["sede_utp"]}')
        print(f'População 2022: {mun["populacao_2022"]}')
        print(f'Impedância 06h: {mun["impedancia_06h"]}')
        print(f'Impedância 2h filtrada: {mun["impedancia_2h_filtrada"]}')
        print(f'Modais:')
        print(f'  - Rodoviária coletiva: {mun["modais"]["rodoviaria_coletiva"]}')
        print(f'  - Rodoviária particular: {mun["modais"]["rodoviaria_particular"]}')
        print(f'  - Aeroviária: {mun["modais"]["aeroviaria"]}')
        print(f'  - Ferroviária: {mun["modais"]["ferroviaria"]}')
        print(f'  - Hidroviária: {mun["modais"]["hidroviaria"]}')
        print(f'Modal Matriz:')
        for modal_name, destinations in mun['modal_matriz'].items():
            print(f'  {modal_name}: {len(destinations)} destinos')
            # Mostrar 3 primeiros destinos
            for i, (dest, trips) in enumerate(list(destinations.items())[:3]):
                print(f'    -> {dest}: {trips} viagens')
        break

print('\n=== EXEMPLO DE UTP ===')
utp = data['utps'][0]
print(f'UTP ID: {utp["utp_id"]}')
print(f'Sede: {utp["sede_cd_mun"]}')
print(f'Total de municípios: {utp["total_municipios"]}')
print(f'Primeiros 5 municípios: {utp["municipios"][:5]}')

print('\n=== METADATA ===')
meta = data['metadata']
print(f'Timestamp: {meta["timestamp"]}')
print(f'Total de municípios: {meta["total_municipios"]}')
print(f'Total de UTPs: {meta["total_utps"]}')
print(f'Fontes: {len(meta["fontes"])} arquivos utilizados')
