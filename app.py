#!/usr/bin/env python3

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

from functions import *

st.set_page_config(layout="wide")

##############################################
# INIT FUNCTIONS
##############################################
def initialize_ee():
    try:
        ee.Initialize()
    except Exception:
        ee.Authenticate()
        ee.Initialize()

@st.cache_data(show_spinner=False)
def load_wayback_data():
    try:
        url = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/WMTS/1.0.0/WMTSCapabilities.xml"
        response = requests.get(url)
        response.raise_for_status()

        root = ET.fromstring(response.content)

        ns = {
            "wmts": "https://www.opengis.net/wmts/1.0",
            "ows": "https://www.opengis.net/ows/1.1",
        }

        layers = root.findall(".//wmts:Contents/wmts:Layer", ns)

        data = []
        for layer in layers:
            title = layer.find("ows:Title", ns)
            resource = layer.find("wmts:ResourceURL", ns)

            data.append({
                "Title": title.text if title is not None else "N/A",
                "ResourceURL_Template": resource.get("template") if resource is not None else "N/A"
            })

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(
            df["Title"].str.extract(r"(\d{4}-\d{2}-\d{2})").squeeze(),
            errors="coerce"
        )
        df.set_index("date", inplace=True)

        return df

    except Exception:
        return pd.DataFrame()

def load_input_data(input_source):
    gdf = get_gdf_from_file_url(input_source)
    gdf = preprocess_gdf(gdf)

    for _, row in gdf.iterrows():
        geometry = pd.DataFrame([row])
        if is_valid_polygon(geometry):
            return gdf, to_best_crs(geometry)

    return None, None

##############################################
# INIT
##############################################
initialize_ee()

##############################################
# HEADER
##############################################
st.markdown("""
<div style="display:flex; justify-content:space-between;">
<img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/Final_IITGN-Logo-symmetric-Color.png" width="100">
<img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/IFS.jpg" width="100">
</div>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align:center;'>Kamlan: KML Analyzer</h1>", unsafe_allow_html=True)

##############################################
# INPUT
##############################################
params = st.query_params
file_url = params.get("file_url", None)
uploaded_file = st.file_uploader("Upload KML/GeoJSON", type=["geojson", "kml"])

input_source = file_url if file_url else uploaded_file

if not input_source:
    st.warning("Please upload a file or provide URL.")
    st.stop()

##############################################
# LOAD GEO DATA (CACHE)
##############################################
if st.session_state.get("cached_file") == input_source:
    input_gdf = st.session_state.input_gdf
    geometry_gdf = st.session_state.geometry_gdf
else:
    input_gdf, geometry_gdf = load_input_data(input_source)

    if geometry_gdf is None:
        st.error("No valid polygon found in file.")
        st.stop()

    st.session_state.input_gdf = input_gdf
    st.session_state.geometry_gdf = geometry_gdf
    st.session_state.cached_file = input_source

##############################################
# LOAD WAYBACK
##############################################
wayback_df = load_wayback_data()

if wayback_df.empty:
    st.error("Failed to load imagery data.")
    st.stop()

first_item = wayback_df.iloc[0]

wayback_title = "Esri " + first_item["Title"]
wayback_url = (
    first_item["ResourceURL_Template"]
    .replace("{TileMatrixSet}", "GoogleMapsCompatible")
    .replace("{TileMatrix}", "{z}")
    .replace("{TileRow}", "{y}")
    .replace("{TileCol}", "{x}")
)

##############################################
# MAP
##############################################
map_type = st.radio(
    "Select Map",
    ["Esri", "Google Hybrid", "Google Satellite"],
    horizontal=True,
)

m = leaf_folium.Map()

if map_type == "Google Hybrid":
    m.add_basemap("HYBRID")
elif map_type == "Google Satellite":
    m.add_basemap("SATELLITE")
else:
    m.add_wms_layer(wayback_url, layers="0", name=wayback_title)

add_geometry_to_maps([m], geometry_gdf)
m.to_streamlit()

##############################################
# METRICS
##############################################
centroid = geometry_gdf.to_crs(4326).centroid.item()

col1, col2 = st.columns(2)
col1.metric("Centroid", f"{centroid.y:.6f}, {centroid.x:.6f}")
col2.metric("Area (ha)", f"{geometry_gdf.area.item()/10000:.2f}")

##############################################
# DEM / SLOPE
##############################################
if "dem_map" not in st.session_state:
    with st.spinner("Loading DEM & Slope..."):
        dem_map, slope_map = get_dem_slope_maps(
            ee.Geometry(geometry_gdf.to_crs(4326).geometry.item().__geo_interface__),
            wayback_url,
            wayback_title,
        )
        st.session_state.dem_map = dem_map
        st.session_state.slope_map = slope_map

cols = st.columns(2)

for col, param_map, title in zip(
    cols,
    [st.session_state.dem_map, st.session_state.slope_map],
    ["DEM Map", "Slope Map"],
):
    with col:
        st.subheader(title)
        param_map.to_streamlit()

##############################################
# VISITOR COUNTER
##############################################
st.session_state.visits = st.session_state.get("visits", 0) + 1

st.markdown("---")
st.write(f"👥 Visitors: {st.session_state.visits}")
