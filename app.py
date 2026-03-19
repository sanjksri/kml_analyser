#!/usr/bin/env python3

##############################################
# Imports
##############################################
import ee
import requests
import pandas as pd
import streamlit as st
import xml.etree.ElementTree as ET
import leafmap.foliumap as leaf_folium
import geopandas as gpd
from shapely.geometry import Polygon
import tempfile
import os

# Must be the first Streamlit command
st.set_page_config(layout="wide")

##############################################
# Simplified Functions
##############################################

def initialize_ee():
    """Initialize Earth Engine with better error handling"""
    try:
        ee.Initialize()
        st.success("✅ Earth Engine initialized successfully")
        return True
    except Exception as e:
        st.warning("⚠️ Earth Engine needs authentication...")
        try:
            ee.Authenticate()
            ee.Initialize()
            st.success("✅ Earth Engine authenticated and initialized")
            return True
        except Exception as e:
            st.error(f"❌ Failed to initialize Earth Engine: {str(e)}")
            st.info("Please run 'earthengine authenticate' in your terminal first")
            return False

@st.cache_data(ttl=3600)
def load_wayback_data():
    """Load Wayback imagery data with error handling"""
    try:
        url = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/WMTS/1.0.0/WMTSCapabilities.xml"
        
        with st.spinner("Loading satellite imagery catalog..."):
            response = requests.get(url, timeout=10)
            response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.content)
        
        # Find all layers
        layers = []
        for elem in root.findall(".//{http://www.opengis.net/wmts/1.0}Layer"):
            title = elem.find("{http://www.opengis.net/ows/1.1}Title")
            resource = elem.find("{http://www.opengis.net/wmts/1.0}ResourceURL")
            
            if title is not None and resource is not None:
                layers.append({
                    "Title": title.text,
                    "URL": resource.get("template")
                })

        if not layers:
            st.warning("No layers found in Wayback data")
            return pd.DataFrame()
        
        # Create DataFrame
        df = pd.DataFrame(layers)
        
        # Extract dates from titles
        dates = []
        for title in df['Title']:
            # Try to find date pattern YYYY-MM-DD
            import re
            match = re.search(r'(\d{4}-\d{2}-\d{2})', title)
            if match:
                dates.append(match.group(1))
            else:
                dates.append(None)
        
        df['date'] = pd.to_datetime(dates)
        df = df.dropna(subset=['date']).sort_values('date', ascending=False)
        
        return df
        
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to load imagery data: {str(e)}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error processing imagery data: {str(e)}")
        return pd.DataFrame()

def load_kml_geojson(file):
    """Load KML or GeoJSON file"""
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp_file:
            tmp_file.write(file.getvalue())
            tmp_path = tmp_file.name
        
        # Read file with geopandas
        gdf = gpd.read_file(tmp_path)
        
        # Clean up
        os.unlink(tmp_path)
        
        if gdf.empty:
            st.error("No geometries found in file")
            return None
        
        # Ensure we have polygons
        if not any(gdf.geometry.type.str.contains('Polygon|MultiPolygon')):
            st.error("File contains no polygon geometries")
            return None
        
        # Filter to keep only polygons
        gdf = gdf[gdf.geometry.type.str.contains('Polygon|MultiPolygon')]
        
        return gdf
        
    except Exception as e:
        st.error(f"Error loading file: {str(e)}")
        return None

def process_wayback_url(url_template):
    """Convert Wayback URL template to Leaflet format"""
    return (url_template
            .replace("{TileMatrixSet}", "GoogleMapsCompatible")
            .replace("{TileMatrix}", "{z}")
            .replace("{TileRow}", "{y}")
            .replace("{TileCol}", "{x}"))

##############################################
# Main App
##############################################

def main():
    # Header
    st.markdown("""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/Final_IITGN-Logo-symmetric-Color.png" width="120">
        <h1 style="color:#2c3e50; margin:0;">🗺️ Kamlan: KML Analyzer</h1>
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/IFS.jpg" width="120">
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize Earth Engine
    ee_initialized = initialize_ee()
    
    # File upload
    uploaded_file = st.file_uploader(
        "📤 Upload KML or GeoJSON file",
        type=["kml", "geojson"],
        help="Upload a file containing polygon geometries"
    )
    
    if uploaded_file is None:
        st.info("👆 Please upload a file to begin")
        st.stop()
    
    # Load the file
    gdf = load_kml_geojson(uploaded_file)
    
    if gdf is None:
        st.stop()
    
    # Display file info
    st.success(f"✅ Loaded {len(gdf)} polygon(s) from file")
    
    # Load Wayback data
    wayback_df = load_wayback_data()
    
    if wayback_df.empty:
        st.error("Could not load satellite imagery. Using default basemap.")
        wayback_url = None
        wayback_title = "Default Imagery"
    else:
        # Use most recent imagery
        latest = wayback_df.iloc[0]
        wayback_title = f"Esri {latest['Title']}"
        wayback_url = process_wayback_url(latest['URL'])
        st.info(f"📅 Latest imagery: {latest['Title']}")
    
    # Map type selection
    map_type = st.radio(
        "🗺️ Select Base Map",
        ["Esri Wayback", "Google Hybrid", "Google Satellite"],
        horizontal=True,
    )
    
    # Create map
    m = leaf_folium.Map(center=[20, 78], zoom_start=5)
    
    # Add basemap
    if map_type == "Google Hybrid":
        m.add_basemap("HYBRID")
    elif map_type == "Google Satellite":
        m.add_basemap("SATELLITE")
    elif map_type == "Esri Wayback" and wayback_url:
        m.add_tile_layer(
            tiles=wayback_url,
            name=wayback_title,
            attribution="Esri"
        )
    else:
        m.add_basemap("SATELLITE")
    
    # Add uploaded geometry
    if not gdf.empty:
        # Convert to GeoJSON
        geojson = gdf.__geo_interface__
        
        # Add to map
        m.add_geojson(
            geojson,
            layer_name="Uploaded Polygon",
            style={
                "color": "red",
                "fillColor": "red",
                "fillOpacity": 0.1,
                "weight": 2
            }
        )
        
        # Zoom to bounds
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
        m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])
    
    # Display map
    st.subheader("📍 Location Map")
    m.to_streamlit(height=500)
    
    # Show metrics
    col1, col2 = st.columns(2)
    
    with col1:
        # Calculate centroid
        centroid = gdf.geometry.centroid.iloc[0]
        st.metric("📍 Centroid", f"{centroid.y:.6f}, {centroid.x:.6f}")
    
    with col2:
        # Calculate area in hectares
        # Convert to projected CRS for accurate area calculation
        gdf_projected = gdf.to_crs("EPSG:3857")
        area_ha = gdf_projected.area.sum() / 10000
        st.metric("📐 Total Area", f"{area_ha:.2f} ha")
    
    # DEM and Slope section (only if EE is initialized)
    if ee_initialized:
        st.markdown("---")
        st.subheader("🏔️ Elevation Analysis")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.info("DEM and slope maps will appear here")
            # Add your DEM function here if available
        
        with col2:
            st.info("Additional analysis tools coming soon")
    
    # Footer with visitor counter
    st.markdown("---")
    if 'visits' not in st.session_state:
        st.session_state.visits = 0
    st.session_state.visits += 1
    
    col1, col2, col3 = st.columns(3)
    with col2:
        st.markdown(f"<p style='text-align:center; color:#666;'>👥 Page Views: {st.session_state.visits}</p>", 
                   unsafe_allow_html=True)

if __name__ == "__main__":
    main()
