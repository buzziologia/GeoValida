
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from main import GeoValidaManager
from src.interface.components.map_viewer import create_interactive_map
import geopandas as gpd

def verify_map():
    print("Initializing Manager...")
    manager = GeoValidaManager()
    
    print("Loading Data...")
    if not manager.step_0_initialize_data():
        print("Failed to load data.")
        return

    print("Syncing Graph with Map...")
    manager.map_generator.sync_with_graph(manager.graph)
    
    gdf_map = manager.map_generator.gdf_complete.copy()
    
    # Ensure WGS84
    if gdf_map.crs != "EPSG:4326":
        print("Reprojecting to EPSG:4326...")
        gdf_map = gdf_map.to_crs(epsg=4326)

    print("Computing Graph Coloring (UTP-based)...")
    coloring = manager.graph.compute_graph_coloring(gdf_map)
    seats = manager.graph.utp_seeds
    
    print(f"Colors used: {len(set(coloring.values()))}")
    
    print("Generating Folium Map...")
    m = create_interactive_map(gdf_map, coloring, seats)
    
    output_file = "verify_map_output.html"
    print(f"Saving to {output_file}...")
    m.save(output_file)
    print("Done.")

if __name__ == "__main__":
    verify_map()
