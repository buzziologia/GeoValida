# Script de diagnóstico para identificar municípios isolados geograficamente
import sys
import io
from pathlib import Path

# Forçar UTF-8 no stdout para Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Adicionar raiz do projeto ao path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import GeoValidaManager
import logging

# Configurar logging para minimal
logging.basicConfig(level=logging.WARNING, format='%(message)s')

def diagnose_isolated_municipalities():
    """Identifica e lista todos os municípios isolados geograficamente."""
    print("=" * 80)
    print("DIAGNOSTICO DE MUNICIPIOS ISOLADOS GEOGRAFICAMENTE")
    print("=" * 80)
    
    # 1. Inicializar manager
    print("\n[1] Inicializando sistema...")
    manager = GeoValidaManager()
    
    if not manager.step_0_initialize_data():
        print("[X] Falha ao carregar dados!")
        return
    
    print("[OK] Dados carregados!")
    
    # 2. Sincronizar mapa com grafo
    print("\n[2] Sincronizando geometrias...")
    gdf = manager.map_generator.sync_with_graph(manager.graph).gdf_complete
    print(f"   GDF: {len(gdf)} municipios")
    
    # 3. Analisar contiguidade de cada UTP
    print("\n[3] Analisando contiguidade por UTP...")
    
    validator = manager.validator
    graph = manager.graph
    
    total_isolated = []
    utps_with_issues = []
    
    # Iterar sobre todas as UTPs que tem sedes definidas
    utp_seeds = graph.utp_seeds
    print(f"   Analisando {len(utp_seeds)} UTPs com sedes definidas...")
    
    for utp_id, sede_id in utp_seeds.items():
        # Filtrar GDF para esta UTP
        gdf_utp = gdf[gdf['UTP_ID'] == utp_id].copy()
        
        if gdf_utp.empty:
            continue
        
        # Validar contiguidade
        isolados = validator.validate_utp_contiguity(utp_id, gdf_utp, sede_id)
        
        if isolados:
            utps_with_issues.append({
                'utp_id': utp_id,
                'sede_id': sede_id,
                'total_muns': len(gdf_utp),
                'isolated_count': len(isolados)
            })
            
            for mun_id in isolados:
                nm_mun = graph.hierarchy.nodes.get(mun_id, {}).get('name', str(mun_id))
                total_isolated.append({
                    'utp_id': utp_id,
                    'cd_mun': mun_id,
                    'nm_mun': nm_mun
                })
    
    # 4. Relatorio
    print("\n" + "=" * 80)
    print("RELATORIO DE MUNICIPIOS ISOLADOS")
    print("=" * 80)
    
    print(f"\n[*] Total de municipios isolados: {len(total_isolated)}")
    print(f"[*] UTPs afetadas: {len(utps_with_issues)}")
    
    if utps_with_issues:
        print("\n[>] UTPs com municipios isolados:")
        for utp in sorted(utps_with_issues, key=lambda x: x['isolated_count'], reverse=True)[:20]:
            print(f"   UTP {utp['utp_id']}: {utp['isolated_count']} isolado(s) de {utp['total_muns']} municipios")
    
    if total_isolated:
        print("\n[>] Lista de municipios isolados (primeiros 50):")
        for item in total_isolated[:50]:
            print(f"   [{item['utp_id']}] {item['nm_mun']} (CD_MUN: {item['cd_mun']})")
        
        if len(total_isolated) > 50:
            print(f"\n   ... e mais {len(total_isolated) - 50} municipios")
    
    # 5. Salvar lista completa em CSV
    output_path = project_root / "data" / "isolated_municipalities.csv"
    import pandas as pd
    df_isolated = pd.DataFrame(total_isolated)
    df_isolated.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig')
    print(f"\n[+] Lista completa salva em: {output_path}")
    
    print("\n" + "=" * 80)
    print("DIAGNOSTICO CONCLUIDO")
    print("=" * 80)

if __name__ == "__main__":
    diagnose_isolated_municipalities()
