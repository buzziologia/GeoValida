import reflex as rx
import sys
import os
from pathlib import Path
import geopandas as gpd
import pandas as pd
import json
import logging
from functools import lru_cache

# --- Setup Paths ---
# Frontend is at: .../geovalida/frontend
# Src is at: .../geovalida/src
# Root is at: .../geovalida

PROJECT_ROOT = Path(__file__).parents[2]
if str(PROJECT_ROOT) not in sys.path:
    # Add project root to sys.path to allow imports from src
    sys.path.append(str(PROJECT_ROOT))

# Import Backend Utilities
from src.interface.map_flow_render import render_map_with_flow_popups
from src.interface.palette import get_palette
from .data_utils import (
    get_municipios_df_cached,
    get_municipalities_gdf_cached,
    get_rm_gdf_cached,
    get_states_gdf_cached,
    get_coloring_cached
)

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



ASSETS_DIR = Path(__file__).parent.parent / "assets"
# Save directly to assets for simpler serving
MAPS_DIR = ASSETS_DIR 
MAPS_DIR.mkdir(parents=True, exist_ok=True)

class MapState(rx.State):
    """State management for the Map Component."""
    
    current_version: str = "8.0"
    is_generating: bool = False
    
    @rx.var
    def map_url(self) -> str:
        """Returns the URL for the current map version."""
        safe_version = "".join(c for c in self.current_version if c.isalnum() or c in ".-_")
        # Served at root because it's in assets/
        return f"/map_{safe_version}.html"

    async def generate_map(self):
        """Background task to generate the map if it doesn't exist."""
        safe_version = "".join(c for c in self.current_version if c.isalnum() or c in ".-_")
        filename = f"map_{safe_version}.html"
        file_path = MAPS_DIR / filename
        
        # Check if exists
        if file_path.exists():
            self.is_generating = False
            return

        # Start generation
        self.is_generating = True
        yield
        
        try:
            # Run generation in thread pool to avoid blocking async loop
            # We can use asyncio.to_thread for this
            import asyncio
            
            # Define synchronous generation function to run in thread
            def _generate():
                df_muni = get_municipios_df_cached()
                gdf = get_municipalities_gdf_cached()
                
                if df_muni is None or gdf is None:
                    return False
                
                # Filter logic would go here
                gdf_filtered = gdf.copy()
                title = f"Versão {self.current_version}"
                
                m = render_map_with_flow_popups(
                    gdf_filtered=gdf_filtered,
                    df_municipios=df_muni,
                    title=title,
                    global_colors=get_coloring_cached(),
                    gdf_rm=get_rm_gdf_cached(),
                    show_rm_borders=True,
                    show_state_borders=True,
                    gdf_states=get_states_gdf_cached(),
                    PASTEL_PALETTE=get_palette(),
                    scroll_wheel_zoom=False  # Disable scroll zoom for Reflex interface
                )
                
                if m:
                    # Manually render and save to avoid potential m.save() threading issues
                    html_content = m.get_root().render()
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    return True
                return False

            # Await the thread
            success = await asyncio.to_thread(_generate)
            
            if not success:
               logger.error("Map generation failed inside thread.")

        except Exception as e:
            logger.error(f"Error in background map generation: {e}", exc_info=True)
        finally:
            self.is_generating = False

    def set_version(self, version: str):
        """Updates the selected map version and triggers generation."""
        self.current_version = version
        return MapState.generate_map
