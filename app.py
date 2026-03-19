#!/usr/bin/env python3

"""
Kamlan: KML Analyzer
A Streamlit application for analyzing KML/GeoJSON files with satellite imagery,
DEM, and slope visualization.
"""

##############################################
# Imports
##############################################
import ee
import requests
import json
import numpy as np
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
import leafmap.foliumap as leaf_folium
from typing import Optional, Tuple, Any
from dataclasses import dataclass
import logging

from functions import *

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Kamlan: KML Analyzer",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

##############################################
# Constants and Configuration
##############################################

@dataclass
class MapConfig:
    """Configuration for map layers"""
    WAYBACK_URL: str = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/WMTS/1.0.0/WMTSCapabilities.xml"
    TILE_MATRIX_SET: str = "GoogleMapsCompatible"
    
class MapTypes:
    """Map type constants"""
    ESRI = "Esri"
    GOOGLE_HYBRID = "Google Hybrid"
    GOOGLE_SATELLITE = "Google Satellite"

##############################################
# INIT FUNCTIONS
##############################################

@st.cache_resource(show_spinner=False)
def initialize_ee() -> None:
    """Initialize Earth Engine with authentication if needed."""
    try:
        ee.Initialize()
        logger.info("Earth Engine initialized successfully")
    except Exception as e:
        logger.info("Earth Engine not initialized, attempting authentication...")
        try:
            ee.Authenticate()
            ee.Initialize()
            logger.info("Earth Engine authenticated and initialized successfully")
        except Exception as auth_error:
            logger.error(f"Failed to authenticate Earth Engine: {auth_error}")
            st.error("Failed to initialize Earth Engine. Please check your authentication.")
            st.stop()

@st.cache_data(ttl=3600, show_spinner=False)
def load_wayback_data() -> pd.DataFrame:
    """
    Load Wayback imagery data from ArcGIS WMTS capabilities.
    
    Returns:
        DataFrame with imagery dates and resource URLs
    """
    try:
        response = requests.get(MapConfig.WAYBACK_URL, timeout=10)
        response.raise_for_status()

        # Parse XML with namespace handling
        root = ET.fromstring(response.content)
        ns = {
            "wmts": "http://www.opengis.net/wmts/1.0",
            "ows": "http://www.opengis.net/ows/1.1",
        }

        layers = root.findall(".//wmts:Contents/wmts:Layer", ns)
        
        data = []
        for layer in layers:
            title_elem = layer.find("ows:Title", ns)
            resource = layer.find("wmts:ResourceURL", ns)
            
            if title_elem is not None and resource is not None:
                data.append({
                    "Title": title_elem.text,
                    "ResourceURL_Template": resource.get("template")
                })

        if not data:
            logger.warning("No layers found in Wayback data")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        
        # Extract and parse dates
        dates = df["Title"].str.extract(r"(\d{4}-\d{2}-\d{2})").squeeze()
        df["date"] = pd.to_datetime(dates, errors="coerce")
        
        # Remove rows with invalid dates and sort
        df = df.dropna(subset=["date"]).sort_values("date", ascending=False)
        df.set_index("date", inplace=True)
        
        logger.info(f"Loaded {len(df)} Wayback imagery dates")
        return df

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Wayback data: {e}")
        return pd.DataFrame()
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML response: {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unexpected error loading Wayback data: {e}")
        return pd.DataFrame()

def load_input_data(input_source: Any) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """
    Load and validate input geospatial data.
    
    Args:
        input_source: Uploaded file or URL
        
    Returns:
        Tuple of (original_gdf, geometry_gdf)
    """
    try:
        gdf = get_gdf_from_file_url(input_source)
        
        if gdf is None or gdf.empty:
            st.error("No valid geometries found in the input file")
            return None, None
            
        gdf = preprocess_gdf(gdf)

        # Find first valid polygon
        for _, row in gdf.iterrows():
            geometry_df = pd.DataFrame([row])
            if is_valid_polygon(geometry_df):
                logger.info("Valid polygon found in input data")
                return gdf, to_best_crs(geometry_df)

        st.error("No valid polygon geometries found in the input file")
        return None, None
        
    except Exception as e:
        logger.error(f"Error loading input data: {e}")
        st.error(f"Failed to load input data: {str(e)}")
        return None, None

def process_wayback_url(row: pd.Series) -> str:
    """
    Process Wayback URL template into Leaflet-compatible format.
    
    Args:
        row: DataFrame row with Title and ResourceURL_Template
        
    Returns:
        Formatted URL for Leaflet
    """
    url_template = row["ResourceURL_Template"]
    return (url_template
            .replace("{TileMatrixSet}", MapConfig.TILE_MATRIX_SET)
            .replace("{TileMatrix}", "{z}")
            .replace("{TileRow}", "{y}")
            .replace("{TileCol}", "{x}"))

##############################################
# UI Components
##############################################

def render_header() -> None:
    """Render application header with logos."""
    st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/Final_IITGN-Logo-symmetric-Color.png" 
             alt="IITGN Logo" 
             style="height:60px; width:auto;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/IFS.jpg" 
             alt="IFS Logo" 
             style="height:60px; width:auto;">
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <h1 style='text-align:center; color:#2c3e50; margin-bottom:2rem;'>
        🗺️ Kamlan: KML Analyzer
    </h1>
    """, unsafe_allow_html=True)

def render_input_section() -> Optional[Any]:
    """
    Render file input section and handle query parameters.
    
    Returns:
        Input source (file or URL) or None
    """
    # Check URL parameters first
    params = st.query_params
    file_url = params.get("file_url", None)
    
    if file_url:
        st.info(f"📎 Loading file from URL: {file_url}")
        return file_url
    
    # File uploader
    uploaded_file = st.file_uploader(
        "📤 Upload KML or GeoJSON file",
        type=["geojson", "kml"],
        help="Upload a file containing polygon geometries"
    )
    
    return uploaded_file

@st.fragment
def render_metrics(geometry_gdf: pd.DataFrame) -> None:
    """
    Render geometry metrics.
    
    Args:
        geometry_gdf: GeoDataFrame with geometry
    """
    centroid = geometry_gdf.to_crs(4326).centroid.item()
    area_ha = geometry_gdf.area.item() / 10000
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(
            "📍 Centroid",
            f"{centroid.y:.6f}, {centroid.x:.6f}",
            help="Center point of the polygon (latitude, longitude)"
        )
    
    with col2:
        st.metric(
            "📐 Area",
            f"{area_ha:.2f} ha",
            help="Total area in hectares"
        )

@st.fragment
def render_dem_slope_maps(geometry_gdf: pd.DataFrame, wayback_url: str, wayback_title: str) -> None:
    """
    Render DEM and slope maps with caching.
    
    Args:
        geometry_gdf: GeoDataFrame with geometry
        wayback_url: Base URL for Wayback imagery
        wayback_title: Title for the imagery layer
    """
    if "dem_map" not in st.session_state or "slope_map" not in st.session_state:
        with st.spinner("🔄 Loading DEM and slope data..."):
            try:
                # Convert geometry to Earth Engine format
                ee_geometry = ee.Geometry(
                    geometry_gdf.to_crs(4326).geometry.item().__geo_interface__
                )
                
                dem_map, slope_map = get_dem_slope_maps(
                    ee_geometry,
                    wayback_url,
                    wayback_title,
                )
                
                st.session_state.dem_map = dem_map
                st.session_state.slope_map = slope_map
                logger.info("DEM and slope maps loaded successfully")
                
            except Exception as e:
                logger.error(f"Failed to load DEM/slope maps: {e}")
                st.error("Failed to load elevation data. Please try again.")
                return

    cols = st.columns(2)
    
    with cols[0]:
        st.subheader("🏔️ Digital Elevation Model")
        if st.session_state.dem_map:
            st.session_state.dem_map.to_streamlit()
        else:
            st.warning("DEM data not available")
    
    with cols[1]:
        st.subheader("📈 Slope Map")
        if st.session_state.slope_map:
            st.session_state.slope_map.to_streamlit()
        else:
            st.warning("Slope data not available")

##############################################
# Main Application
##############################################

def main():
    """Main application entry point."""
    
    # Initialize
    initialize_ee()
    
    # Header
    render_header()
    
    # Input section
    input_source = render_input_section()
    
    if not input_source:
        st.info("👆 Please upload a file or provide a URL to begin analysis")
        st.stop()
    
    # Load geospatial data
    if st.session_state.get("cached_file") != input_source:
        with st.spinner("📊 Loading and validating geospatial data..."):
            input_gdf, geometry_gdf = load_input_data(input_source)
            
            if geometry_gdf is None:
                st.error("❌ No valid polygon found in the uploaded file")
                st.stop()
            
            # Cache in session state
            st.session_state.input_gdf = input_gdf
            st.session_state.geometry_gdf = geometry_gdf
            st.session_state.cached_file = input_source
            
            # Clear dependent cached data
            if "dem_map" in st.session_state:
                del st.session_state.dem_map
            if "slope_map" in st.session_state:
                del st.session_state.slope_map
    
    # Load Wayback imagery data
    with st.spinner("🛰️ Loading satellite imagery catalog..."):
        wayback_df = load_wayback_data()
    
    if wayback_df.empty:
        st.error("❌ Failed to load satellite imagery data")
        st.stop()
    
    # Get most recent imagery
    first_item = wayback_df.iloc[0]
    wayback_title = f"Esri {first_item['Title']}"
    wayback_url = process_wayback_url(first_item)
    
    # Map type selection
    map_type = st.radio(
        "🗺️ Select Base Map",
        [MapTypes.ESRI, MapTypes.GOOGLE_HYBRID, MapTypes.GOOGLE_SATELLITE],
        horizontal=True,
        help="Choose the base map layer for visualization"
    )
    
    # Initialize and display map
    m = leaf_folium.Map()
    
    if map_type == MapTypes.GOOGLE_HYBRID:
        m.add_basemap("HYBRID")
    elif map_type == MapTypes.GOOGLE_SATELLITE:
        m.add_basemap("SATELLITE")
    else:
        m.add_wms_layer(wayback_url, layers="0", name=wayback_title)
    
    # Add geometry to map
    add_geometry_to_maps([m], st.session_state.geometry_gdf)
    
    # Display map
    m.to_streamlit(height=500)
    
    # Metrics
    render_metrics(st.session_state.geometry_gdf)
    
    # DEM and Slope maps
    st.markdown("---")
    render_dem_slope_maps(
        st.session_state.geometry_gdf,
        wayback_url,
        wayback_title
    )
    
    # Visitor counter
    st.markdown("---")
    st.session_state.visits = st.session_state.get("visits", 0) + 1
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown(
            f"<div style='text-align:center; color:#7f8c8d;'>"
            f"👥 Page Views: {st.session_state.visits}</div>",
            unsafe_allow_html=True
        )

if __name__ == "__main__":
    main()
