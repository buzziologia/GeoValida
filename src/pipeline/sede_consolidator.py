import logging
import pandas as pd
import geopandas as gpd
import networkx as nx
import json
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from src.core.graph import TerritorialGraph
from src.core.validator import TerritorialValidator
from src.interface.consolidation_manager import ConsolidationManager
from src.pipeline.sede_analyzer import SedeAnalyzer

class SedeConsolidator:
    """
    Step 6: Consolidation of Sedes based on functional dependency (2h distance + flow)
    and infrastructure scoring (Airport + Tourism).
    """

    def __init__(self, graph: TerritorialGraph, validator: TerritorialValidator, sede_analyzer: SedeAnalyzer):
        self.graph = graph
        self.validator = validator
        self.analyzer = sede_analyzer
        self.logger = logging.getLogger("GeoValida.SedeConsolidator")
        self.consolidation_manager = ConsolidationManager()
        self.adjacency_graph = None  # Will be built from GDF
        
        # Set data directory for exports
        from pathlib import Path
        self.data_dir = Path(__file__).parent.parent.parent / "data" / "03_processed"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _build_adjacency_graph(self, gdf: gpd.GeoDataFrame):
        """Builds a NetworkX graph representing spatial adjacency of municipalities."""
        self.logger.info("Building spatial adjacency graph for pathfinding...")
        self.adjacency_graph = nx.Graph()
        
        if gdf is None or gdf.empty:
            return

        # Ensure we have geometries
        gdf_valid = gdf[gdf.geometry.notna()]
        
        # Use touching/intersection with small buffer to find neighbors
        # Optimized approach: sjoin
        # Project to estimate buffer if needed, but assuming GDF is suitable
        # Using a small buffer helps with imperfect topologies
        
        # Project to metric CRS for buffering (EPSG:3857 is fast and sufficient for adjacency)
        gdf_valid_metric = gdf_valid.to_crs(epsg=3857)
        
        # Use a small buffer (e.g., 100 meters) to handle topology gaps
        buffer_val = 100.0 
        gdf_buff = gdf_valid_metric.copy()
        gdf_buff['geometry'] = gdf_buff.geometry.buffer(buffer_val)
        
        # Self-join to find neighbors
        # Use simple index-based join on metric/buffered geometries
        sjoin = gpd.sjoin(gdf_buff, gdf_buff, how='inner', predicate='intersects')
        
        edges = []
        for idx, row in sjoin.iterrows():
             left = int(row['CD_MUN_left'])
             right = int(row['CD_MUN_right'])
             if left != right:
                 edges.append((left, right))
                 
        self.adjacency_graph.add_edges_from(edges)
        self.logger.info(f"Adjacency graph built: {self.adjacency_graph.number_of_nodes()} nodes, {self.adjacency_graph.number_of_edges()} edges.")


    def _get_regic_rank(self, regic_val: str) -> int:
        """
        Returns numeric rank for REGIC description. Lower is MORE important/relevant.
        Based on standard IBGE hierarchy.
        """
        if not regic_val: return 99
        
        r = str(regic_val).lower().strip()
        
        # Hierarchy Definition (1 = Most Relevant)
        mapping = {
            'grande metrópole nacional': 1,
            'metrópole nacional': 2,
            'metrópole': 3,
            'capital regional a': 4,
            'capital regional b': 5,
            'capital regional c': 6,
            'centro sub-regional a': 7,
            'centro sub-regional b': 8,
            'centro de zona a': 9,
            'centro de zona b': 10,
            'centro local': 11
        }
        
        for k, v in mapping.items():
            if k in r:
                return v
                
        return 99 # Unknown

    def _get_sede_score(self, sede_metrics: Dict) -> int:
        """Calculates score (0-2) based on Airport and Tourism."""
        score = 0
        if sede_metrics.get('tem_aeroporto'):
            score += 1
        
        # Check tourism class.
        # User defined: "1 - Município Turístico"
        turismo = str(sede_metrics.get('turismo', '')).strip()
        if "1 - Município Turístico" in turismo: 
             score += 1
             
        return score

    def _validate_utp_adjacency(self, utp_origem: str, utp_destino: str) -> bool:
        """
        Validates if two UTPs are adjacent (share a border).
        Required to maintain territorial continuity.
        
        IMPORTANT: Adjacency is between UTPs, not between sedes.
        Checks if ANY municipality from origin UTP is adjacent to 
        ANY municipality from destination UTP.
        """
        if self.adjacency_graph is None:
            self.logger.warning("Adjacency graph not built yet!")
            return False
        
        # Get all municipalities in each UTP
        muns_origem = []
        muns_destino = []
        
        for node, data in self.graph.hierarchy.nodes(data=True):
            if data.get('type') == 'municipality':
                node_utp = self.graph.get_municipality_utp(node)
                if node_utp == utp_origem:
                    muns_origem.append(node)
                elif node_utp == utp_destino:
                    muns_destino.append(node)
        
        # Check if any municipality from origem is adjacent to any from destino
        for mun_orig in muns_origem:
            if mun_orig in self.adjacency_graph:
                neighbors = self.adjacency_graph[mun_orig]
                for mun_dest in muns_destino:
                    if mun_dest in neighbors:
                        return True
        
        return False

    def _filter_candidates(self, df_metrics: pd.DataFrame) -> List[Dict]:
        """
        Filters potential consolidation candidates based on simplified rules:
        1. Sede must have main flow to another sede
        2. Travel time <= 2 hours
        3. RM rule: same RM OR both without RM
        4. UTPs must be adjacent
        5. Destination score >= Origin score
        """
        candidates = []
        rejected = []
        
        # Track filtering statistics
        filter_stats = {
            'total_checked': 0,
            'no_alert': 0,
            'invalid_destination': 0,
            'same_utp': 0,
            'travel_time_exceeded': 0,
            'rm_mismatch': 0,
            'not_adjacent': 0,
            'rejected_by_score': 0,
            'accepted': 0
        }
        
        for _, row in df_metrics.iterrows():
            filter_stats['total_checked'] += 1
            
            # Must have dependency alert
            if not row['tem_alerta_dependencia']:
                filter_stats['no_alert'] += 1
                continue
                
            sede_origem = row['cd_mun_sede']
            utp_origem = row['utp_id']
            sede_destino = row['principal_destino_cd']
            
            # Validate destination exists
            if pd.isna(sede_destino):
                filter_stats['invalid_destination'] += 1
                continue
            
            utp_destino = self.graph.get_municipality_utp(sede_destino)
            
            # Check if same UTP (Ensure strict string comparison)
            if str(utp_origem) == str(utp_destino):
                filter_stats['same_utp'] += 1
                continue

            # RULE 1: Travel time <= 2 hours
            tempo_viagem = row.get('tempo_ate_destino_h')
            if tempo_viagem is None or tempo_viagem > 2.0:
                filter_stats['travel_time_exceeded'] += 1
                rejected.append({
                    'sede_origem': sede_origem,
                    'nm_origem': row['nm_sede'],
                    'utp_origem': utp_origem,
                    'sede_destino': sede_destino,
                    'utp_destino': utp_destino,
                    'motivo_rejeicao': f'Tempo de viagem {tempo_viagem:.2f}h > 2h'
                })
                continue

            # RULE 2: RM consistency
            rm_origem = str(row.get('regiao_metropolitana', '')).strip()
            if rm_origem.lower() == 'nan':
                rm_origem = ''
            
            # Get RM of destination sede
            sede_utp_destino = self.graph.utp_seeds.get(utp_destino)
            if not sede_utp_destino:
                filter_stats['invalid_destination'] += 1
                rejected.append({
                    'sede_origem': sede_origem,
                    'nm_origem': row['nm_sede'],
                    'utp_origem': utp_origem,
                    'sede_destino': sede_destino,
                    'utp_destino': utp_destino,
                    'motivo_rejeicao': 'UTP destino não tem sede ativa'
                })
                continue
            
            dest_row = df_metrics[df_metrics['cd_mun_sede'] == sede_utp_destino]
            if dest_row.empty:
                filter_stats['invalid_destination'] += 1
                rejected.append({
                    'sede_origem': sede_origem,
                    'nm_origem': row['nm_sede'],
                    'utp_origem': utp_origem,
                    'sede_destino': sede_destino,
                    'utp_destino': utp_destino,
                    'motivo_rejeicao': 'Sede destino não encontrada em métricas'
                })
                continue
            
            dest_row = dest_row.iloc[0]
            rm_destino = str(dest_row.get('regiao_metropolitana', '')).strip()
            if rm_destino.lower() == 'nan':
                rm_destino = ''

            # RM Rule: Both without RM OR same RM
            if rm_origem or rm_destino:  # At least one has RM
                if rm_origem != rm_destino:
                    filter_stats['rm_mismatch'] += 1
                    rejected.append({
                        'sede_origem': sede_origem,
                        'nm_origem': row['nm_sede'],
                        'utp_origem': utp_origem,
                        'sede_destino': sede_destino,
                        'utp_destino': utp_destino,
                        'rm_origem': rm_origem,
                        'rm_destino': rm_destino,
                        'motivo_rejeicao': f"RM incompatível: '{rm_origem}' != '{rm_destino}'"
                    })
                    continue

            # RULE 3: UTP Adjacency
            if not self._validate_utp_adjacency(utp_origem, utp_destino):
                filter_stats['not_adjacent'] += 1
                rejected.append({
                    'sede_origem': sede_origem,
                    'nm_origem': row['nm_sede'],
                    'utp_origem': utp_origem,
                    'sede_destino': sede_destino,
                    'utp_destino': utp_destino,
                    'motivo_rejeicao': 'UTPs não são adjacentes'
                })
                continue
            
            # RULE 4: Score validation
            score_origem = self._get_sede_score(row)
            score_destino = self._get_sede_score(dest_row)
            
            # Destination must have better or equal infrastructure
            if score_destino < score_origem:
                filter_stats['rejected_by_score'] += 1
                rejected.append({
                    'sede_origem': sede_origem,
                    'nm_origem': row['nm_sede'],
                    'utp_origem': utp_origem,
                    'sede_destino': sede_destino,
                    'nm_destino': dest_row['nm_sede'],
                    'utp_destino': utp_destino,
                    'score_origem': score_origem,
                    'score_destino': score_destino,
                    'tempo_viagem_h': tempo_viagem,
                    'rm_origem': rm_origem,
                    'rm_destino': rm_destino,
                    'motivo_rejeicao': f'Score destino ({score_destino}) < origem ({score_origem})'
                })
                continue
            
            # APPROVED!
            filter_stats['accepted'] += 1
            candidates.append({
                'sede_origem': sede_origem,
                'nm_origem': row['nm_sede'],
                'utp_origem': utp_origem,
                'sede_destino': sede_destino,
                'nm_destino': dest_row['nm_sede'],
                'utp_destino': utp_destino,
                'score_origem': score_origem,
                'score_destino': score_destino,
                'tempo_viagem_h': tempo_viagem,
                'rm_origem': rm_origem,
                'rm_destino': rm_destino,
                'motivo_rejeicao': ''
            })
        
        # Log statistics
        self.logger.info(f"\n📈 Candidate Filtering Statistics:")
        self.logger.info(f"   Total sedes checked: {filter_stats['total_checked']}")
        self.logger.info(f"   Filtered out - No dependency alert: {filter_stats['no_alert']}")
        self.logger.info(f"   Filtered out - Invalid destination: {filter_stats['invalid_destination']}")
        self.logger.info(f"   Filtered out - Same UTP: {filter_stats['same_utp']}")
        self.logger.info(f"   Filtered out - Travel time > 2h: {filter_stats['travel_time_exceeded']}")
        self.logger.info(f"   Filtered out - RM mismatch: {filter_stats['rm_mismatch']}")
        self.logger.info(f"   Filtered out - UTPs not adjacent: {filter_stats['not_adjacent']}")
        self.logger.info(f"   Filtered out - Rejected by score: {filter_stats['rejected_by_score']}")
        self.logger.info(f"   ✅ Accepted candidates: {filter_stats['accepted']}")
        
        # Store rejected for CSV export
        self.rejected_candidates = rejected
        
        return candidates

    def _sync_analyzer_with_graph(self):
        """Syncs the analyzer's DataFrame with the current graph state (UTPs and Sedes)."""
        if self.analyzer.df_municipios is None:
            return

        self.logger.info("Syncing Analyzer with Graph State...")
        
        # Build a set of all sede municipalities for fast lookup
        # graph.utp_seeds is a dict: {utp_id: mun_id_sede}
        sede_municipalities = set(self.graph.utp_seeds.values())
        
        updates = {}
        for node in self.graph.hierarchy.nodes():
             # We assume integer nodes are municipalities
             if isinstance(node, int) or (isinstance(node, str) and node.isdigit()):
                 # Verify it is a municipality node (or just trust ID)
                 mun_id = int(node)
                 
                 # Get UTP
                 utp = self.graph.get_municipality_utp(mun_id)
                 
                 # Get Sede Status - check if this municipality is a sede
                 # A municipality is a sede if it's a value in utp_seeds
                 is_sede = mun_id in sede_municipalities
                 
                 updates[mun_id] = {'utp_id': utp, 'sede_utp': is_sede}
        
        # Bulk Update DataFrame
        # Iterate updates is safer/faster than df iterrows for this
        sede_count = 0
        for idx, row in self.analyzer.df_municipios.iterrows():
            mun_id = int(row['cd_mun'])
            if mun_id in updates:
                self.analyzer.df_municipios.at[idx, 'utp_id'] = updates[mun_id]['utp_id']
                self.analyzer.df_municipios.at[idx, 'sede_utp'] = updates[mun_id]['sede_utp']
                if updates[mun_id]['sede_utp']:
                    sede_count += 1
        
        self.logger.info(f"✅ Synced {len(updates)} municipalities. {sede_count} are sedes.")

        # Force analyzer to clear cached metrics if any
        # (calculate_socioeconomic_metrics recalculates from df_municipios every time, so this is sufficient)

    def run_sede_consolidation(self, flow_df: pd.DataFrame, gdf: gpd.GeoDataFrame, map_gen) -> int:
        """
        Executes Simplified Sede Consolidation Pipeline (Single Pass).
        
        Logic:
        1. Identify sedes with main flow to another sede (travel time <= 2h)
        2. Validate RM rules (same RM or both without RM)
        3. Validate UTP adjacency
        4. Validate infrastructure scores
        5. Move entire UTP (sede + all municipalities) to destination UTP
        """
        self.logger.info("Starting Step 6: Sede Consolidation (Simplified)...")
        
        # Initialize
        self.consolidation_manager = ConsolidationManager()
        self.changes_current_run = []
        self.rejected_candidates = []
        
        # Build Adjacency Graph
        self._build_adjacency_graph(gdf)
        
        # Sync analyzer with current graph state
        self._sync_analyzer_with_graph()
        
        # Calculate metrics for all sedes
        df_metrics = self.analyzer.calculate_socioeconomic_metrics()
        
        total_sedes = len(df_metrics)
        sedes_com_alerta = df_metrics['tem_alerta_dependencia'].sum() if 'tem_alerta_dependencia' in df_metrics.columns else 0
        
        self.logger.info(f"📊 Sede Analysis Stats:")
        self.logger.info(f"   Total sedes: {total_sedes}")
        self.logger.info(f"   Sedes with dependency alerts: {sedes_com_alerta}")
        
        if total_sedes == 0:
            self.logger.warning("⚠️  NO SEDES FOUND!")
            self._save_results_and_csv()
            return 0
        
        # Filter candidates using simplified rules
        candidates = self._filter_candidates(df_metrics)
        
        # Resolve mutual preference conflicts (A -> B and B -> A).
        # When two sedes prefer each other, only allow the movement of the one
        # whose total originating flow is smaller. If flows are equal, reject both
        # to avoid mutual loss of sede status.
        if candidates and flow_df is not None:
            mapping = {str(c['sede_origem']): str(c['sede_destino']) for c in candidates}
            to_remove = set()
            for c in candidates:
                a = str(c['sede_origem'])
                b = str(c['sede_destino'])
                # Check reciprocal
                if b in mapping and mapping[b] == a:
                    # Already decided
                    if a in to_remove or b in to_remove:
                        continue

                    try:
                        flow_a = float(self._get_total_flow(int(a), flow_df) or 0)
                    except Exception:
                        flow_a = 0.0
                    try:
                        flow_b = float(self._get_total_flow(int(b), flow_df) or 0)
                    except Exception:
                        flow_b = 0.0

                    if flow_a == flow_b:
                        # Tie: reject both
                        to_remove.update([a, b])
                        reason = f'Concorrência recíproca com mesmo fluxo ({flow_a}); nenhum movido.'
                    elif flow_a > flow_b:
                        # A has larger flow (is bigger/stronger).
                        # We want to KEEP A (reject move A->B) and EXECUTE move B->A.
                        # Matches candidate where sede_origem = A
                        to_remove.add(a) 
                        reason = f'Concorrência: {a} tem fluxo maior ({flow_a}) que {b} ({flow_b}); {a} deve ser MANTIDO (removemos A->B) e {b} deve mover (mantemos B->A).'
                    else:
                        # B has larger flow.
                        # We want to KEEP B (reject move B->A) and EXECUTE move A->B.
                        # Matches candidate where sede_origem = B
                        to_remove.add(b)
                        reason = f'Concorrência: {b} tem fluxo maior ({flow_b}) que {a} ({flow_a}); {b} deve ser MANTIDO (removemos B->A) e {a} deve mover (mantemos A->B).'

                    # Register rejected candidate(s)
                    for rem in ( [a, b] if flow_a == flow_b else ([b] if flow_a > flow_b else [a]) ):
                        # find candidate dict
                        rem_cand = next((x for x in candidates if str(x['sede_origem']) == str(rem)), None)
                        if rem_cand:
                            self.rejected_candidates.append({
                                'sede_origem': rem_cand.get('sede_origem', ''),
                                'nm_origem': rem_cand.get('nm_origem', ''),
                                'utp_origem': rem_cand.get('utp_origem', ''),
                                'sede_destino': rem_cand.get('sede_destino', ''),
                                'utp_destino': rem_cand.get('utp_destino', ''),
                                'motivo_rejeicao': reason
                            })

            if to_remove:
                before_count = len(candidates)
                candidates = [c for c in candidates if str(c['sede_origem']) not in to_remove]
                self.logger.info(f"🔁 Resolved {len(to_remove)} reciprocal candidate(s): {to_remove}. Candidates reduced {before_count}->{len(candidates)}")
        elif candidates and flow_df is None:
            self.logger.warning('Fluxo de viagens (flow_df) não fornecido: não foi possível resolver concorrências recíprocas automaticamente.')
        if not candidates:
            self.logger.info("✅ No consolidation candidates found.")
            self._save_results_and_csv()
            return 0
        
        self.logger.info(f"✅ Found {len(candidates)} consolidation candidates")
        
        # Execute consolidations
        total_changes = 0
        
        for cand in candidates:
            sede_origem = cand['sede_origem']
            sede_destino = cand['sede_destino'] if 'sede_destino' in cand else None
            utp_origem = cand['utp_origem']
            utp_destino = cand['utp_destino']
            
            self.logger.info(f"\n🔄 Consolidating: {cand['nm_origem']} (UTP {utp_origem}) -> {cand['nm_destino']} (UTP {utp_destino})")
            
            # Get all municipalities in the origin UTP
            muns_to_move = []
            for node, data in self.graph.hierarchy.nodes(data=True):
                if data.get('type') == 'municipality':
                    # FIX: Type mismatch (int vs str) caused failure to find municipalities
                    if str(self.graph.get_municipality_utp(node)) == str(utp_origem):
                        muns_to_move.append(node)
            
            self.logger.info(f"  Moving entire UTP: {len(muns_to_move)} municipalities from {utp_origem} to {utp_destino}")

            # Preserve original membership to detect full vs partial moves
            original_muns = set(muns_to_move)

            # Move all municipalities
            for mun in muns_to_move:
                self.graph.move_municipality(mun, utp_destino)
                self.logger.debug(f"DEBUG: Moved municipality {mun} from UTP {utp_origem} to UTP {utp_destino}")
                
                # Update GDF for this municipality
                if gdf is not None and 'CD_MUN' in gdf.columns:
                    try:
                        mask = gdf['CD_MUN'].astype(str).str.split('.').str[0] == str(mun)
                        gdf.loc[mask, 'UTP_ID'] = str(utp_destino)
                    except Exception as e:
                        self.logger.error(f"    Failed to update GDF for {mun}: {e}")
            
            # Log consolidation
            cons_entry = self.consolidation_manager.add_consolidation(
                source_utp=utp_origem,
                target_utp=utp_destino,
                reason=f"Sede consolidation (full UTP): Score {cand['score_origem']}->{cand['score_destino']}, Travel {cand['tempo_viagem_h']:.2f}h",
                details={
                    "sede_id": sede_origem,
                    "is_sede": True,  # FIX: Add flag so it appears in CSV
                    "nm_sede": cand['nm_origem'],
                    "municipalities_moved": len(muns_to_move),
                    "score_origem": cand['score_origem'],
                    "score_destino": cand['score_destino'],
                    "tempo_viagem_h": cand['tempo_viagem_h'],
                    "rm_origem": cand.get('rm_origem', ''),
                    "rm_destino": cand.get('rm_destino', '')
                }
            )
            self.changes_current_run.append(cons_entry)
            

            # Revoga status de sede apenas se a sede de origem realmente mudou de UTP
            if sede_origem in muns_to_move and str(self.graph.get_municipality_utp(sede_origem)) == str(utp_destino):
                if self.graph.hierarchy.has_node(sede_origem):
                    self.logger.debug(f"DEBUG: Revoking sede flag for municipality {sede_origem} (UTP {utp_origem} -> {utp_destino})")
                    self.graph.hierarchy.nodes[sede_origem]['sede_utp'] = False

                # Decide corretamente sobre o mapeamento de seeds e remoção de UTP
                utp_node = f"UTP_{utp_origem}"

                # Recalcula sucessores da UTP após a movimentação
                successors = list(self.graph.hierarchy.successors(utp_node)) if self.graph.hierarchy.has_node(utp_node) else []

                # Identify remaining municipalities
                remaining_muns = [n for n in successors if self.graph.hierarchy.nodes[n].get('type') == 'municipality']

                # Se a UTP ficou vazia --> remover seed e nó
                if not remaining_muns:
                    if str(utp_origem) in self.graph.utp_seeds:
                        self.logger.debug(f"DEBUG: Deleting utp_seeds[{utp_origem}] -> {self.graph.utp_seeds.get(str(utp_origem))}")
                        del self.graph.utp_seeds[str(utp_origem)]
                    if self.graph.hierarchy.has_node(utp_node):
                        self.logger.debug(f"DEBUG: Removing UTP node {utp_node} from hierarchy (empty after move)")
                        self.graph.hierarchy.remove_node(utp_node)
                else:
                    # Partial move: apenas reatribuir seed se a seed atual não pertence mais à UTP
                    if str(utp_origem) in self.graph.utp_seeds:
                        current_seed = self.graph.utp_seeds[str(utp_origem)]
                        if (not self.graph.hierarchy.has_node(current_seed)) or (current_seed not in remaining_muns):
                            # Escolher nova sede: preferir município já marcado como sede, senão o primeiro
                            new_sede = None
                            for m in remaining_muns:
                                if self.graph.hierarchy.nodes[m].get('sede_utp'):
                                    new_sede = m
                                    break
                            if new_sede is None and remaining_muns:
                                new_sede = remaining_muns[0]

                            if new_sede is not None:
                                self.logger.debug(f"DEBUG: Reassigning seed for UTP {utp_origem} -> {new_sede} (was {current_seed})")
                                self.graph.utp_seeds[str(utp_origem)] = new_sede
                                if self.graph.hierarchy.has_node(new_sede):
                                    self.graph.hierarchy.nodes[new_sede]['sede_utp'] = True
                    else:
                        # No seed recorded previously: set one from remaining
                        if remaining_muns:
                            new_sede = remaining_muns[0]
                            self.logger.debug(f"DEBUG: Setting missing seed for UTP {utp_origem} -> {new_sede}")
                            self.graph.utp_seeds[str(utp_origem)] = new_sede
                            if self.graph.hierarchy.has_node(new_sede):
                                self.graph.hierarchy.nodes[new_sede]['sede_utp'] = True

            # GARANTIR QUE A UTP DE DESTINO SEMPRE TERÁ UMA SEDE REGISTRADA
            # Se não houver sede registrada para a UTP destino, definir a sede_destino (ou sede_origem se apropriado)
            utp_destino_str = str(utp_destino)
            if utp_destino_str not in self.graph.utp_seeds or not self.graph.hierarchy.has_node(self.graph.utp_seeds[utp_destino_str]):
                # Preferir sede_destino se ela está entre os municípios da UTP destino
                if sede_destino in muns_to_move and str(self.graph.get_municipality_utp(sede_destino)) == utp_destino_str:
                    self.logger.debug(f"DEBUG: Setting utp_seeds[{utp_destino_str}] -> {sede_destino} (preferred destination sede)")
                    self.graph.utp_seeds[utp_destino_str] = sede_destino
                    if self.graph.hierarchy.has_node(sede_destino):
                        self.graph.hierarchy.nodes[sede_destino]['sede_utp'] = True
                # Se não, usar sede_origem se ela foi movida para a UTP destino
                elif sede_origem in muns_to_move and str(self.graph.get_municipality_utp(sede_origem)) == utp_destino_str:
                    self.logger.debug(f"DEBUG: Setting utp_seeds[{utp_destino_str}] -> {sede_origem} (sede_origem moved into destino)")
                    self.graph.utp_seeds[utp_destino_str] = sede_origem
                    if self.graph.hierarchy.has_node(sede_origem):
                        self.graph.hierarchy.nodes[sede_origem]['sede_utp'] = True
                # Como fallback, escolher qualquer município da UTP destino
                elif muns_to_move:
                    mun_fallback = muns_to_move[0]
                    self.logger.debug(f"DEBUG: Fallback setting utp_seeds[{utp_destino_str}] -> {mun_fallback}")
                    self.graph.utp_seeds[utp_destino_str] = mun_fallback
                    if self.graph.hierarchy.has_node(mun_fallback):
                        self.graph.hierarchy.nodes[mun_fallback]['sede_utp'] = True
            
            total_changes += 1
            self.logger.info(f"  ✅ Sede consolidation complete: {len(muns_to_move)} municipalities moved")

        
        # Save results
        self._save_results_and_csv()
        
        # Recolor graph
        self.logger.info("\n🎨 Recalculating graph coloring...")
        try:
            coloring = self.graph.compute_graph_coloring(gdf)
            self.logger.info(f"✅ Coloring updated: {max(coloring.values(), default=0) + 1} colors needed")
            
            if gdf is not None:
                gdf['COLOR_ID'] = gdf['CD_MUN'].astype(int).map(coloring)
            
            # Save coloring
            # Imports moved to top of file
            
            coloring_file = self.data_dir / "post_sede_coloring.json"
            coloring_str_keys = {str(k): v for k, v in coloring.items()}
            
            with open(coloring_file, 'w') as f:
                json.dump(coloring_str_keys, f, indent=2)
            
            self.logger.info(f"💾 Coloring saved to: {coloring_file}")
            
            # CRITICAL: Confirm all active seeds are marked as sede_utp=True in graph nodes
            # This ensures the snapshot reflects the final consolidation state
            count_sedes_marked = 0
            for utp_id, mun_id in self.graph.utp_seeds.items():
                if self.graph.hierarchy.has_node(mun_id):
                    self.graph.hierarchy.nodes[mun_id]['sede_utp'] = True
                    count_sedes_marked += 1
            self.logger.info(f"✅ Marked {count_sedes_marked} municipalities as Active Sedes in Graph.")

            # Export Snapshot Step 6 (Sede Consolidation)
            snapshot_path = self.data_dir / "snapshot_step6_sede_consolidation.json"
            self.graph.export_snapshot(snapshot_path, "Sede Consolidation", gdf)
            
        except Exception as e:
            self.logger.warning(f"⚠️  Error recalculating coloring or saving snapshot: {e}")
        
        self.logger.info(f"\n✅ Sede Consolidation complete: {total_changes} consolidations executed")
        return total_changes

    def _save_results_and_csv(self):
        """Save consolidation results to JSON and CSV files."""
        import pandas as pd
        from pathlib import Path
        
        # Save JSON (existing functionality)
        self.logger.info(f"💾 Saving consolidation results ({len(self.changes_current_run)} changes)...")
        self.consolidation_manager.save_sede_batch(self.changes_current_run if self.changes_current_run else [])
        
        # Generate CSV with all candidates (approved + rejected)
        csv_records = []
        
        # Add approved consolidations
        for change in self.changes_current_run:
            if change.get('details', {}).get('is_sede', False):  # Only record sede movements, not individual municipalities
                # Backwards-compatible: some entries use 'mun_id', others use 'sede_id'
                sede_origem_id = change['details'].get('mun_id', change['details'].get('sede_id', ''))
                csv_records.append({
                    'sede_origem': sede_origem_id,
                    'utp_origem': change['source_utp'],
                    'sede_destino': change['details'].get('sede_destino', ''),
                    'utp_destino': change['target_utp'],
                    'tempo_viagem_h': change['details'].get('tempo_viagem_h', ''),
                    'score_origem': change['details'].get('score_origem', ''),
                    'score_destino': change['details'].get('score_destino', ''),
                    'rm_origem': change['details'].get('rm_origem', ''),
                    'rm_destino': change['details'].get('rm_destino', ''),
                    'status': 'APROVADO',
                    'motivo_rejeicao': ''
                })
        
        # Add rejected candidates
        for rejected in self.rejected_candidates:
            csv_records.append({
                'sede_origem': rejected.get('sede_origem', ''),
                'utp_origem': rejected.get('utp_origem', ''),
                'sede_destino': rejected.get('sede_destino', ''),
                'utp_destino': rejected.get('utp_destino', ''),
                'tempo_viagem_h': rejected.get('tempo_viagem_h', ''),
                'score_origem': rejected.get('score_origem', ''),
                'score_destino': rejected.get('score_destino', ''),
                'rm_origem': rejected.get('rm_origem', ''),
                'rm_destino': rejected.get('rm_destino', ''),
                'status': 'REJEITADO',
                'motivo_rejeicao': rejected.get('motivo_rejeicao', '')
            })
        
        # Save CSV
        if csv_records:
            df_csv = pd.DataFrame(csv_records)
            csv_path = Path(self.data_dir) / 'sede_consolidation_result.csv'
            df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig')
            self.logger.info(f"💾 CSV saved to: {csv_path} ({len(csv_records)} records)")
        else:
            self.logger.info("No consolidation records to save to CSV")




    def _get_total_flow(self, mun_id: int, flow_df: pd.DataFrame) -> float:
        """Helper to get total flow originating from a municipality."""
        if flow_df is None: return 0
        return flow_df[flow_df['mun_origem'] == mun_id]['viagens'].sum()

    def _export_candidate_analysis_json(self, df_metrics, candidates, pass_num):
        '''Exporta análise detalhada de candidatos para JSON.'''
        import json
        from pathlib import Path
        from datetime import datetime
        
        export_data = {
            'pass_number': pass_num,
            'timestamp': datetime.now().isoformat(),
            'total_sedes_analyzed': len(df_metrics),
            'total_candidates_found': len(candidates),
            'candidates': []
        }
        
        for cand in candidates:
            sede_origem = cand['sede_origem']
            sede_destino = cand['sede_destino']
            origem_row = df_metrics[df_metrics['cd_mun_sede'] == sede_origem]
            dest_row = df_metrics[df_metrics['cd_mun_sede'] == sede_destino]
            if origem_row.empty or dest_row.empty:
                continue
            origem_row = origem_row.iloc[0]
            dest_row = dest_row.iloc[0]
            candidate_data = {
                'approved': True,
                'origem': {'cd_mun': int(sede_origem), 'nm_mun': origem_row['nm_sede'], 'utp_id': cand['utp_origem'], 'uf': origem_row['uf'], 'populacao': int(origem_row['populacao_total_utp']), 'regic': origem_row['regic'], 'tem_aeroporto': bool(origem_row['tem_aeroporto']), 'aeroporto_icao': origem_row.get('aeroporto_icao', ''), 'turismo': origem_row.get('turismo', ''), 'score': cand['score_origem']},
                'destino': {'cd_mun': int(sede_destino), 'nm_mun': dest_row['nm_sede'], 'utp_id': cand['utp_destino'], 'uf': dest_row['uf'], 'populacao': int(dest_row['populacao_total_utp']), 'regic': dest_row['regic'], 'tem_aeroporto': bool(dest_row['tem_aeroporto']), 'aeroporto_icao': dest_row.get('aeroporto_icao', ''), 'turismo': dest_row.get('turismo', ''), 'score': cand['score_dest']},
                'fluxo': {'principal_destino': origem_row.get('principal_destino_nm', ''), 'tempo_h': float(origem_row.get('tempo_ate_destino_h', 0)), 'proporcao': float(origem_row.get('proporcao_fluxo_principal', 0))},
                'reason': cand['reason']
            }
            export_data['candidates'].append(candidate_data)
        output_path = Path(self.data_dir) / f'sede_consolidation_analysis_pass{pass_num}.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        self.logger.info(f'✅ Análise exportada: {output_path}')
        return output_path

