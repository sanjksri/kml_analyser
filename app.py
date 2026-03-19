#!/usr/bin/env python3

##############################################
# Imports
##############################################
import os
from datetime import datetime
import ee
import json
import numpy as np
import geemap.foliumap as gee_folium
import leafmap.foliumap as leaf_folium
import streamlit as st
import pandas as pd
import plotly.express as px
import branca.colormap as cm
import xml.etree.ElementTree as ET
import requests

from functions import *

st.set_page_config(layout="wide")

##############################################
# SAFE EARTH ENGINE INIT
##############################################
try:
    ee.Initialize()
except Exception:
    ee.Authenticate()
    ee.Initialize()

############################################
# HEADER
############################################
st.write(
    """
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/Final_IITGN-Logo-symmetric-Color.png" style="width: 10%;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/IFS.jpg" style="width: 10%;">
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<h1 style='text-align:center;'>Kamlan: KML Analyzer</h1>", unsafe_allow_html=True)

############################################
# FILE INPUT (FIXED)
############################################
params = st.query_params
file_url = params.get("file_url", None)
uploaded_file = st.file_uploader("Upload KML/GeoJSON", type=["geojson", "kml"])

if file_url:
    input_source = file_url
elif uploaded_file:
    input_source = uploaded_file
else:
    st.warning("Upload file or provide URL")
    st.stop()

############################################
# LOAD DATA
############################################
if ("cached_file_url" in st.session_state) and (st.session_state.cached_file_url == input_source):
    input_gdf = st.session_state.input_gdf
    geometry_gdf = st.session_state.geometry_gdf
else:
    input_gdf = get_gdf_from_file_url(input_source)
    input_gdf = preprocess_gdf(input_gdf)

    # FIXED geometry loop
    for _, row in input_gdf.iterrows():
        geometry_gdf = pd.DataFrame([row])
        if is_valid_polygon(geometry_gdf):
            break
    else:
        st.error("No polygon found")
        st.stop()

    geometry_gdf = to_best_crs(geometry_gdf)

    st.session_state.input_gdf = input_gdf
    st.session_state.geometry_gdf = geometry_gdf
    st.session_state.cached_file_url = input_source

############################################
# WAYBACK DATA (SAFE)
############################################
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

    layer_data = []
    for layer in layers:
        title = layer.find("ows:Title", ns)
        resource = layer.find("wmts:ResourceURL", ns)

        layer_data.append({
            "Title": title.text if title is not None else "N/A",
            "ResourceURL_Template": resource.get("template") if resource is not None else "N/A"
        })

    wayback_df = pd.DataFrame(layer_data)
    wayback_df["date"] = pd.to_datetime(
        wayback_df["Title"].str.extract(r"(\d{4}-\d{2}-\d{2})").squeeze(),
        errors="coerce"
    )
    wayback_df.set_index("date", inplace=True)

    if wayback_df.empty:
        st.error("Wayback data unavailable")
        st.stop()

except Exception:
    st.error("Wayback loading failed")
    st.stop()

############################################
# MAP DISPLAY
############################################
first_item = wayback_df.iloc[0]

wayback_title = "Esri " + first_item["Title"]
wayback_url = (
    first_item["ResourceURL_Template"]
    .replace("{TileMatrixSet}", "GoogleMapsCompatible")
    .replace("{TileMatrix}", "{z}")
    .replace("{TileRow}", "{y}")
    .replace("{TileCol}", "{x}")
)

map_type = st.radio(
    "",
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

############################################
# BASIC METRICS
############################################
centroid = geometry_gdf.to_crs(4326).centroid.item()

st.write(f"📍 Centroid: {centroid.y:.6f}, {centroid.x:.6f}")
st.write(f"📐 Area (ha): {geometry_gdf.area.item()/10000:.2f}")

############################################
# DEM CACHE FIX
############################################
if "dem_map" not in st.session_state:
    dem_map, slope_map = get_dem_slope_maps(
        ee.Geometry(geometry_gdf.to_crs(4326).geometry.item().__geo_interface__),
        wayback_url,
        wayback_title,
    )
    st.session_state.dem_map = dem_map
    st.session_state.slope_map = slope_map

############################################
# DISPLAY DEM
############################################
cols = st.columns(2)

for col, param_map, title in zip(
    cols,
    [st.session_state.dem_map, st.session_state.slope_map],
    ["DEM", "Slope"],
):
    with col:
        param_map.to_streamlit()

############################################
# VISITOR COUNTER (SAFE)
############################################
if "visits" not in st.session_state:
    st.session_state.visits = 0

st.session_state.visits += 1
st.markdown("---")
st.write(f"👥 Visitors: {st.session_state.visits}")

############################################
# END
############################################
