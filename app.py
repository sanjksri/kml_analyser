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

from functions import *
import xml.etree.ElementTree as ET

st.set_page_config(layout="wide")

############################################
# IITGN and GDF Logo
############################################
st.write(
    f"""
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/Final_IITGN-Logo-symmetric-Color.png"  style="width: 10%; margin-right: auto;">
        <img src="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG/resolve/main/IFS.jpg" style="width: 10%; margin-left: auto;">
    </div>
    """,
    unsafe_allow_html=True,
)

############################################
# Title
############################################

st.markdown(
    f"""
    <h1 style="text-align: center;">Kamlan: KML Analyzer</h1>
    """,
    unsafe_allow_html=True,
)

############################################
# KML/GeoJSON input
############################################

# Input: GeoJSON/KML file
file_url = st.query_params.get("file_url", None)
if file_url is None:
    file_url = st.file_uploader("Upload KML/GeoJSON file", type=["geojson", "kml"])

if file_url is None:
    st.warning(
        "Please provide a KML or GeoJSON URL as a query parameter, e.g., `https://sustainabilitylabiitgn-ndvi-perg.hf.space?file_url=<your_file_url>` or upload a file."
    )
    force_stop()

# process the file

if ("cached_file_url" in st.session_state) and (st.session_state.cached_file_url == file_url):
    input_gdf = st.session_state.input_gdf
    geometry_gdf = st.session_state.geometry_gdf
else:
    input_gdf = get_gdf_from_file_url(file_url)
    input_gdf = preprocess_gdf(input_gdf)

    for i in range(len(input_gdf)):
        geometry_gdf = input_gdf[input_gdf.index == i]
        if is_valid_polygon(geometry_gdf):
            break
    else:
        st.error(f"No polygon found inside KML. Please check the KML file.")
        force_stop()

    geometry_gdf = to_best_crs(geometry_gdf)
    st.session_state.input_gdf = input_gdf
    st.session_state.geometry_gdf = geometry_gdf
    st.session_state.cached_file_url = file_url

############################################
# App
############################################
container = st.container()
# metrics_view_placeholder = st.empty()
# view_on_google_maps_placeholder = st.empty()
# download_metrics_placeholder = st.empty()
# dem_placeholder = st.empty()

with st.expander("Advanced Settings"):
    st.write("Select the vegetation indices to calculate:")
    all_veg_indices = ["GujEVI", "NDVI", "EVI", "EVI2", "RandomForest", "GujVDI", "MNDWI", "SAVI", "MVI", "NBR", "GCI"]
    formulas = {
        "GujEVI": r"$0.5 \times \frac{NIR - Red}{NIR + 6 \times Red - 8.25 \times Blue + 0.01}, \text{(Optimized EVI for Gujarat)}$",
        "NDVI": r"$\frac{NIR - Red}{NIR + Red}$",
        "EVI": r"$G \times \frac{NIR - Red}{NIR + C1 \times Red - C2 \times Blue + L}$",
        "EVI2": r"$G \times \frac{NIR - Red}{NIR + L + C \times Red}$",
        "RandomForest": "ML based Classification",
        "GujVDI": r"$2.29 \times \frac{-3.98 \left(\frac{Blue}{NIR}\right) + 12.54 \left(\frac{Green}{NIR}\right) - 5.49 \left(\frac{Red}{NIR}\right) - 0.19}{-21.87 \left(\frac{Blue}{NIR}\right) + 12.4 \left(\frac{Green}{NIR}\right) + 19.98 \left(\frac{Red}{NIR}\right) + 1}$",
        "MNDWI": r"$\frac{Green - SWIR}{Green + SWIR}$",
        "SAVI": r"$\frac{(1 + L) \times (NIR - Red)}{NIR + Red + L}, \text{ where } L=0.5$",
        "MVI": r"$\frac{NIR - (Green + SWIR)}{NIR + (Green + SWIR)}$",
        "NBR": r"$\frac{NIR - SWIR2}{NIR + SWIR2}$",
        "GCI": r"$\frac{NIR - Green}{Green}$",
    }
    defaults = [False, True, False, False, False, False, False, False, False, False, False]
    veg_indices = []
    for veg_index, default in zip(all_veg_indices, defaults):
        if st.checkbox(f"{veg_index} = {formulas[veg_index]}", value=default):
            veg_indices.append(veg_index)
    st.write("Select the parameters for the EVI/EVI2 calculation (default is as per EVI's Wikipedia page)")
    cols = st.columns(5)
    evi_vars = {}
    for col, name, default in zip(cols, ["G", "C1", "C2", "L", "C"], [2.5, 6, 7.5, 1, 2.4]):
        value = col.number_input(f"{name}", value=default)
        evi_vars[name] = value

    # Date range input
    max_year = datetime.now().year
    jan_1 = pd.to_datetime(f"{max_year}/01/01", format="%Y/%m/%d")
    dec_31 = pd.to_datetime(f"{max_year}/12/31", format="%Y/%m/%d")
    nov_15 = pd.to_datetime(f"{max_year}/11/15", format="%Y/%m/%d")
    dec_15 = pd.to_datetime(f"{max_year}/12/15", format="%Y/%m/%d")
    input_daterange = st.date_input(
        'Date Range (Ignore year. App will compute indices for this date range in each year starting from "Minimum Year" to "Maximum Year")',
        (nov_15, dec_15),
        jan_1,
        dec_31,
    )
    cols = st.columns(2)
    with cols[0]:
        min_year = int(st.number_input("Minimum Year", value=2019, min_value=2015, step=1))
    with cols[1]:
        max_year = int(st.number_input("Maximum Year", value=max_year, min_value=2015, step=1))

    buffer = st.number_input("Buffer (m)", value=50, min_value=0, step=1)

if len(input_gdf) > 1:
    with container:
        st.warning(f"Only the first polygon in the KML is processed; all other geometries are ignored.")

outer_geometry_gdf = geometry_gdf.copy()
outer_geometry_gdf["geometry"] = outer_geometry_gdf["geometry"].buffer(buffer)
buffer_geometry_gdf = (
    outer_geometry_gdf.difference(geometry_gdf).reset_index().drop(columns="index")
)  # reset index forces GeoSeries to GeoDataFrame
buffer_geometry_gdf["Name"] = "Buffer"

# Get Wayback data
# <old code>
# wayback_df = pd.read_parquet("./wayback.parquet").set_index("date")
# </old code>
# <new code 2nd Feb 2025 by Zeel>
# Fetch XML data
url = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/WMTS/1.0.0/WMTSCapabilities.xml"
response = requests.get(url)
response.raise_for_status()  # Ensure request was successful

# Parse XML
root = ET.fromstring(response.content)

ns = {
    "wmts": "https://www.opengis.net/wmts/1.0",
    "ows": "https://www.opengis.net/ows/1.1",
    "xlink": "https://www.w3.org/1999/xlink",
}

layers = root.findall(".//wmts:Contents/wmts:Layer", ns)

layer_data = []
for layer in layers:
    title = layer.find("ows:Title", ns)
    identifier = layer.find("ows:Identifier", ns)
    resource = layer.find("wmts:ResourceURL", ns)  # Tile URL template

    title_text = title.text if title is not None else "N/A"
    identifier_text = identifier.text if identifier is not None else "N/A"
    url_template = resource.get("template") if resource is not None else "N/A"

    layer_data.append({"Title": title_text, "ResourceURL_Template": url_template})

wayback_df = pd.DataFrame(layer_data)
wayback_df["date"] = pd.to_datetime(wayback_df["Title"].str.extract(r"(\d{4}-\d{2}-\d{2})").squeeze(), errors="coerce")
wayback_df.set_index("date", inplace=True)
print(wayback_df)

# </new code 2nd Feb 2025 by Zeel>

# visualize the geometry
first_item = wayback_df.iloc[0]
wayback_title = "Esri " + first_item["Title"]
wayback_url = (
    first_item["ResourceURL_Template"]
    .replace("{TileMatrixSet}", "GoogleMapsCompatible")
    .replace("{TileMatrix}", "{z}")
    .replace("{TileRow}", "{y}")
    .replace("{TileCol}", "{x}")
)
# print(wayback_url)

with container:
    map_type = st.radio(
        "",
        ["Esri Satellite Map", "Google Hybrid Map (displays place names)", "Google Satellite Map"],
        horizontal=True,
    )
    m = leaf_folium.Map()
    if map_type == "Google Hybrid Map (displays place names)":
        write_info("Google Hybrid Map (displays place names)", center_align=True)
        m.add_basemap("HYBRID")
    elif map_type == "Google Satellite Map":
        write_info("Google Satellite Map", center_align=True)
        m.add_basemap("SATELLITE")
    elif map_type == "Esri Satellite Map":
        write_info(wayback_title, center_align=True)
        m.add_wms_layer(
            wayback_url,
            layers="0",
            name=wayback_title,
            attribution="Esri",
        )
    else:
        st.error("Invalid map type")
        force_stop()

    add_geometry_to_maps([m], geometry_gdf, buffer_geometry_gdf, opacity=0.3)
    m.to_streamlit()

# Generate stats
centroid = geometry_gdf.to_crs(4326).centroid.item()
centroid_lon = centroid.xy[0][0]
centroid_lat = centroid.xy[1][0]
stats_df = pd.DataFrame(
    {
        "Area (m^2)": geometry_gdf.area.item(),
        "Perimeter (m)": geometry_gdf.length.item(),
        "Points": str(json.loads(geometry_gdf.to_crs(4326).to_json())["features"][0]["geometry"]["coordinates"]),
        "Centroid": f"({centroid_lat:.6f}, {centroid_lon:.6f})",
    },
    index=[0],
)

gmaps_redirect_url = f"http://maps.google.com/maps?q={centroid_lat},{centroid_lon}&layer=satellite"
with container:
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center;">
            <table style="border-collapse: collapse; text-align: center;">
                <tr>
                    <th style="border: 1px solid black; text-align: left;">Metric</th>
                    <th style="border: 1px solid black; text-align: right;">Value</th>
                    <th style="border: 1px solid black; text-align: left;">Unit</th>
                </tr>
                <tr>
                    <td style="border: 1px solid black; text-align: left;">Area</td>
                    <td style="border: 1px solid black; text-align: right;">{stats_df['Area (m^2)'].item()/10000:.2f}</td>
                    <td style="border: 1px solid black; text-align: left;">ha</td>
                </tr>
                <tr>
                    <td style="border: 1px solid black; text-align: left;">Perimeter</td>
                    <td style="border: 1px solid black; text-align: right;">{stats_df['Perimeter (m)'].item():.2f}</td>
                    <td style="border: 1px solid black; text-align: left;">m</td>
                </tr>
                <tr>
                    <td style="border: 1px solid black; text-align: left;">Centroid</td>
                    <td style="border: 1px solid black; text-align: right;">({centroid_lat:.6f}, {centroid_lon:.6f})</td>
                    <td style="border: 1px solid black; text-align: left;">(lat, lon)</td>
            </table>
        </div>
        <div style="text-align: center; margin-bottom: 10px;">
            <a href="{gmaps_redirect_url}" target="_blank">
            <button>View on Google Maps</button>
        </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

stats_csv = stats_df.to_csv(index=False)
with container:
    st.download_button(
        "Download Geometry Metrics", stats_csv, "geometry_metrics.csv", "text/csv", use_container_width=True
    )

# Run one-time setup
if "one_time_setup_done" not in st.session_state:
    one_time_setup()
    st.session_state.one_time_setup_done = True

if ("cached_dem_maps" in st.session_state) and (st.session_state.cached_file_url == file_url):
    dem_map = st.session_state.dem_map
    slope_map = st.session_state.slope_map
else:
    dem_map, slope_map = get_dem_slope_maps(
        ee.Geometry(geometry_gdf.to_crs(4326).geometry.item().__geo_interface__), wayback_url, wayback_title
    )
    st.session_state.dem_map = dem_map
    st.session_state.slope_map = slope_map
    st.session_state.cached_dem_maps = True

with container:
    st.write(
        "<h3><div style='text-align: center;'>DEM and Slope from SRTM at 30m resolution</div></h3>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for col, param_map, title in zip(cols, [dem_map, slope_map], ["DEM Map", "Slope Map"]):
        with col:
            param_map.add_gdf(
                geometry_gdf,
                layer_name="Geometry",
                style_function=lambda x: {"color": "blue", "fillOpacity": 0.0, "fillColor": "blue"},
            )
            write_info(f"""<div style="text-align: center;">{title}</div>""")
            param_map.addLayerControl()
            param_map.to_streamlit()

st.info("ℹ️ After adjusting settings (if required), press the button below to generate the analysis.")

# Submit
m = st.markdown(
    """
<style>
div.stButton > button:first-child {
    background-color: #006400;
    color:#ffffff;
}
</style>""",
    unsafe_allow_html=True,
)
submit = st.button("Calculate Vegetation Indices", use_container_width=True)

# Derived Inputs
ee_geometry = ee.Geometry(geometry_gdf.to_crs(4326).geometry.item().__geo_interface__)
ee_feature_collection = ee.FeatureCollection(ee_geometry)
buffer_ee_geometry = ee.Geometry(buffer_geometry_gdf.to_crs(4326).geometry.item().__geo_interface__)
buffer_ee_feature_collection = ee.FeatureCollection(buffer_ee_geometry)
outer_ee_geometry = ee.Geometry(outer_geometry_gdf.to_crs(4326).geometry.item().__geo_interface__)
outer_ee_feature_collection = ee.FeatureCollection(outer_ee_geometry)

if submit:
    satellites = {
        "COPERNICUS/S2_SR_HARMONIZED": {
            "scale": 10,
            "collection": ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .select(
                ["B2", "B3", "B4", "B8", "B11", "B12", "MSK_CLDPRB", "TCI_R", "TCI_G", "TCI_B"],
                ["Blue", "Green", "Red", "NIR", "SWIR", "SWIR2", "MSK_CLDPRB", "R", "G", "B"],
            )
            .map(lambda image: add_indices(image, nir_band="NIR", red_band="Red", blue_band="Blue", green_band="Green", 
                                           swir_band="SWIR", swir2_band = "SWIR2", evi_vars=evi_vars)),
        },
    }
    satellite = list(satellites.keys())[0]
    st.session_state.satellites = satellites
    st.session_state.satellite = satellite

    # Input: Satellite Sources
    st.markdown(f"Satellite source: `{satellite}`")
    satellite_selected = {}
    for satellite in satellites:
        satellite_selected[satellite] = satellite

    st.write("<h2><div style='text-align: center;'>Results</div></h2>", unsafe_allow_html=True)
    if not any(satellite_selected.values()):
        st.error("Please select at least one satellite source")
        force_stop()

    # Create range
    start_day = input_daterange[0].day
    start_month = input_daterange[0].month
    end_day = input_daterange[1].day
    end_month = input_daterange[1].month

    dates = []
    for year in range(min_year, max_year + 1):
        start_date = pd.to_datetime(f"{year}-{start_month:02d}-{start_day:02d}")
        end_date = pd.to_datetime(f"{year}-{end_month:02d}-{end_day:02d}")
        dates.append((start_date, end_date))

    result_df = pd.DataFrame()
    for satellite, attrs in satellites.items():
        if not satellite_selected[satellite]:
            continue

        with st.spinner(f"Processing {satellite} ..."):
            progress_bar = st.progress(0)
            for i, daterange in enumerate(dates):
                process_date(
                    daterange,
                    satellite,
                    veg_indices,
                    satellites,
                    buffer_ee_geometry,
                    ee_feature_collection,
                    buffer_ee_feature_collection,
                    result_df,
                )
                progress_bar.progress((i + 1) / len(dates))

    st.session_state.result = result_df

print("Printing result...")
if "result" in st.session_state:
    try:
        result_df = st.session_state.result
        satellites = st.session_state.satellites
        satellite = st.session_state.satellite
    
        print(result_df.columns)
    
        # drop rows with all NaN values
        result_df = result_df.dropna(how="all")
        # drop columns with all NaN values
        result_df = result_df.dropna(axis=1, how="all")
        print(result_df.columns)
        print(result_df.head(2))
    
        # df.reset_index(inplace=True)
        # df.index = pd.to_datetime(df["index"], format="%Y-%m")
        for column in result_df.columns:
            result_df[column] = pd.to_numeric(result_df[column], errors="ignore")
    
        df_numeric = result_df.select_dtypes(include=["float64"])
        # df_numeric.index.name = "Date Range"
        html = df_numeric.style.format(precision=2).set_properties(**{"text-align": "right"}).to_html()
        st.write(
            f"""<div style="display: flex; justify-content: center;">
                 {html}</div>""",
            unsafe_allow_html=True,
        )
        df_numeric_csv = df_numeric.to_csv(index=True)
        st.download_button(
            "Download Time Series Data", df_numeric_csv, "vegetation_indices.csv", "text/csv", use_container_width=True
        )
    
        df_numeric.index = [daterange_str_to_year(daterange) for daterange in df_numeric.index]
        for veg_index in veg_indices:
            # fig = px.line(df_numeric, y=[veg_index, f"{veg_index}_buffer", f"{veg_index}_ratio"], markers=True)
            # fig.update_layout(xaxis=dict(tickvals=df_numeric.index, ticktext=df_numeric.index))
            # st.plotly_chart(fig)

            # Dynamically find which columns exist in the DataFrame for the current veg_index
            cols_to_plot = [
                col
                for col in [veg_index, f"{veg_index}_buffer", f"{veg_index}_ratio"]
                if col in df_numeric.columns
            ]

            # Only create a plot if there is at least one valid column to plot
            if cols_to_plot:
                fig = px.line(
                    df_numeric,
                    y=cols_to_plot,
                    markers=True,
                    title=f"Time Series for {veg_index}",
                )
                fig.update_layout(
                    xaxis_title="Year",
                    yaxis_title="Index Value",
                    xaxis=dict(tickvals=df_numeric.index, ticktext=df_numeric.index),
                    legend_title_text="Metric"
                )
                st.plotly_chart(fig, use_container_width=True)
    
        st.write(
            "<h3><div style='text-align: center;'>Visual Comparison between Two Years</div></h3>", unsafe_allow_html=True
        )
        cols = st.columns(2)
    
        with cols[0]:
            year_1 = st.selectbox("Year 1", result_df.index, index=0, format_func=lambda x: daterange_str_to_year(x))
        with cols[1]:
            year_2 = st.selectbox(
                "Year 2", result_df.index, index=len(result_df.index) - 1, format_func=lambda x: daterange_str_to_year(x)
            )
    
        for veg_index in veg_indices:
            st.write(f"<h3><div style='text-align: center;'>{veg_index}</div></h3>", unsafe_allow_html=True)
            cols = st.columns(2)
            for col, daterange_str in zip(cols, [year_1, year_2]):
                mosaic = result_df.loc[daterange_str, f"mosaic_{veg_index}"]
                with col:
                    m = gee_folium.Map()
                    m.add_tile_layer(
                        wayback_url,
                        name=wayback_title,
                        attribution="Esri",
                    )
                    veg_index_layer = gee_folium.ee_tile_layer(mosaic, {"bands": [veg_index], "min": 0, "max": 1})
    
                    if satellite == "COPERNICUS/S2_SR_HARMONIZED":
                        min_all = 0
                        max_all = 255
                    else:
                        raise ValueError(f"Unknown satellite: {satellite}")
    
                    if veg_index == "Test":
                        bins = [-1, 0, 0.1, 0.2, 0.3, 0.4, 0.5, 1]
                        histogram, bin_edges = get_histogram(veg_index, mosaic.select(veg_index), ee_geometry, bins)
                        total_pix = np.sum(histogram)
                        formatted_histogram = [f"{h*100/total_pix:.2f}" for h in histogram]
                        print(histogram, bin_edges, bins, formatted_histogram)
                        m.add_legend(
                            title="NDVI Class/Value",
                            legend_dict={
                                "<0:Waterbody ({}%)".format(formatted_histogram[0]): "#0000FF",
                                "0-0.1: Open ({}%)".format(formatted_histogram[1]): "#FF0000",
                                "0.1-0.2: Highly Degraded ({}%)".format(formatted_histogram[2]): "#FFFF00",
                                "0.2-0.3: Degraded ({}%)".format(formatted_histogram[3]): "#FFA500",
                                "0.3-0.4: Moderately Degraded ({}%)".format(formatted_histogram[4]): "#00FE00",
                                "0.4-0.5: Dense ({}%)".format(formatted_histogram[5]): "#00A400",
                                ">0.5: Very Dense ({}%)".format(formatted_histogram[6]): "#006D00",
                            },
                            position="bottomright",
                            draggable=False,
                        )
                        ndvi_vis_params = {
                            "min": -0.1,
                            "max": 0.6,
                            "palette": ["#0000FF", "#FF0000", "#FFFF00", "#FFA500", "#00FE00", "#00A400", "#006D00"],
                        }
                        m.add_layer(mosaic.select(veg_index).clip(outer_ee_geometry), ndvi_vis_params)
    
                    elif veg_index in ["NDVI", "RandomForest", "GujVDI", "GujEVI", "EVI", "EVI2", "SAVI"]:
                        bins = [0,0.2,0.4,0.6,0.8,1]
                        histogram, bin_edges = get_histogram(veg_index, mosaic.select(veg_index), ee_geometry, bins)
                        total_pix = np.sum(histogram)
                        formatted_histogram = [f"{h*100/total_pix:.2f}" for h in histogram]
                        print(histogram, bin_edges, bins, formatted_histogram)
                        m.add_legend(
                            title=f"{veg_index} Class/Value",
                            legend_dict={
                                #"<0:Waterbody ({}%)".format(formatted_histogram[0]): "#0000FF",
                                "0-0.2: Open/Sparse Vegetation Density ({}%)".format(formatted_histogram[0]): "#FF0000",
                                "0.2-0.4: Low Vegetation Density ({}%)".format(formatted_histogram[1]): "#FFFF00",
                                "0.4-0.6: Moderate Vegetation Density ({}%)".format(formatted_histogram[2]): "#FFA500",
                                "0.6-0.8: Dense Vegetation ({}%)".format(formatted_histogram[3]): "#00FE00",
                                "0.8-1: Very Dense Vegetation ({}%)".format(formatted_histogram[4]): "#00A400",
                                #">0.5: Very Dense ({}%)".format(formatted_histogram[6]): "#006D00",
                            },
                            position="bottomright",
                            draggable=False,
                        )
                        ind_vis_params = {
                            "min": 0,
                            "max": 1,
                            "palette": ["#FF0000", "#FFFF00", "#FFA500", "#00FE00", "#00A400"],
                        }
                        m.add_layer(mosaic.select(veg_index).clip(outer_ee_geometry), ind_vis_params)
    
                    elif veg_index in ["MNDWI"]:
                        bins = [-0.8, -0.6, -0.4, -0.2, 0.0, 0.2, 1]
                        histogram, bin_edges = get_histogram(veg_index, mosaic.select(veg_index), ee_geometry, bins)
                        total_pix = np.sum(histogram)
                        formatted_histogram = [f"{h*100/total_pix:.2f}" for h in histogram]
                        print(histogram, bin_edges, bins, formatted_histogram)
                        m.add_legend(
                            title=f"{veg_index} Class/Value",
                            legend_dict={
                                #"<0:Waterbody ({}%)".format(formatted_histogram[0]): "#0000FF",
                                "-0.8 to -0.6:  ({}%)".format(formatted_histogram[0]): "#FF0000",
                                "-0.6 to -0.4: ({}%)".format(formatted_histogram[1]): "#FFFF00",
                                "-0.4 to -0.2:  ({}%)".format(formatted_histogram[2]): "#FFA500",
                                "-0.2 to 0.0: ({}%)".format(formatted_histogram[3]): "#00FE00",
                                "0.0 to 0.2:  ({}%)".format(formatted_histogram[4]): "#00A400",
                                ">0.2: Very Dense ({}%)".format(formatted_histogram[5]): "#006D00",
                            },
                            position="bottomright",
                            draggable=False,
                        )
                        ind_vis_params = {
                            "min": -0.8,
                            "max": 1,
                            "palette": ["#FF0000", "#FFFF00", "#FFA500", "#00FE00", "#00A400", "#006D00"],
                        }
                        m.add_layer(mosaic.select(veg_index).clip(outer_ee_geometry), ind_vis_params)
    
                    elif veg_index in ["NBR"]:
                        bins = [-1, 0.1, 0.275, 0.45, 0.65, 1]
                        histogram, bin_edges = get_histogram(veg_index, mosaic.select(veg_index), ee_geometry, bins)
                        total_pix = np.sum(histogram)
                        formatted_histogram = [f"{h*100/total_pix:.2f}" for h in histogram]
                        print(histogram, bin_edges, bins, formatted_histogram)
                        m.add_legend(
                            title=f"{veg_index} Class/Value",
                            legend_dict={
                                #"<0:Waterbody ({}%)".format(formatted_histogram[0]): "#0000FF",
                                "-1 to 0.1: Unburned ({}%)".format(formatted_histogram[0]): "#00A400" ,
                                "0.1 to 0.275: Low-severity burn ({}%)".format(formatted_histogram[1]): "#00FE00",
                                "0.275 to 0.45: Moderate-to-low severity burn ({}%)".format(formatted_histogram[2]): "#FFA500",
                                "0.45 to 0.66: Moderate-to-high severity burn ({}%)".format(formatted_histogram[3]): "#FFFF00",
                                "0.66 to 1:  High-severity burn ({}%)".format(formatted_histogram[4]): "#FF0000",
                            },
                            position="bottomright",
                            draggable=False,
                        )
                        ind_vis_params = {
                            "min": -1,
                            "max": 1,
                            "palette": ["#FF0000", "#FFFF00", "#FFA500", "#00FE00", "#00A400", "#006D00"],
                        }
                        m.add_layer(mosaic.select(veg_index).clip(outer_ee_geometry), ind_vis_params)
    
                    
                    else:
                        # For GCI
                        vis_params = {"min": 1, "max": 10, "palette": ["white", "green"]}  
                        colormap = cm.LinearColormap(colors=vis_params["palette"], vmin=vis_params["min"], vmax=vis_params["max"])
                        m.add_layer(mosaic.select(veg_index).clip(outer_ee_geometry), vis_params)
                        m.add_child(colormap)
                    
                    add_geometry_to_maps([m], geometry_gdf, buffer_geometry_gdf)
                    m.to_streamlit()
    
        st.write("<h3><div style='text-align: center;'>Esri RGB Imagery</div></h3>", unsafe_allow_html=True)
        cols = st.columns(2)
        for col, daterange_str in zip(cols, [year_1, year_2]):
            start_date, end_date = daterange_str_to_dates(daterange_str)
            mid_date = start_date + (end_date - start_date) / 2
            esri_date = min(wayback_df.index, key=lambda x: abs(x - mid_date))
            esri_url = (
                wayback_df.loc[esri_date, "ResourceURL_Template"]
                .replace("{TileMatrixSet}", "GoogleMapsCompatible")
                .replace("{TileMatrix}", "{z}")
                .replace("{TileRow}", "{y}")
                .replace("{TileCol}", "{x}")
            )
            esri_title = "Esri " + wayback_df.loc[esri_date, "Title"]
            with col:
                m = leaf_folium.Map()
                m.add_tile_layer(
                    esri_url,
                    name=esri_title,
                    attribution="Esri",
                )
                add_geometry_to_maps([m], geometry_gdf, buffer_geometry_gdf)
                write_info(
                    f"""
                <div style="text-align: center;">
                    Esri Imagery - {esri_date.strftime('%Y-%m-%d')}
                </div>
                """
                )
                m.to_streamlit()
    
        for name, key in zip(
            ["RGB (Least Cloud Tile Crop)", "RGB (Max NDVI Mosaic)"],
            ["image_visual_least_cloud", "mosaic_visual_max_ndvi"],
        ):
            st.write(f"<h3><div style='text-align: center;'>{name}</div></h3>", unsafe_allow_html=True)
            cols = st.columns(2)
            for col, daterange_str in zip(cols, [year_1, year_2]):
                start_date, end_date = daterange_str_to_dates(daterange_str)
                mid_date = start_date + (end_date - start_date) / 2
                with col:
                    m = gee_folium.Map()
                    visual_mosaic = result_df.loc[daterange_str, key]
                    # visual_layer = gee_folium.ee_tile_layer(mosaic, {"bands": ["R", "G", "B"], "min": min_all, "max": max_all})
    
                    m.add_layer(visual_mosaic.select(["R", "G", "B"]))
                    add_geometry_to_maps([m], geometry_gdf, buffer_geometry_gdf)
                    m.to_streamlit()
    
    except KeyError as e:
        st.error(
            f"🛑 Please press the **'Calculate Vegetation Indices'** button again to refresh the analysis."
        )
        st.stop()

show_visitor_counter('counter.txt')
show_credits()
