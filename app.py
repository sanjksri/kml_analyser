import re
import json
import streamlit as st
import pandas as pd
import geopandas as gpd
import leafmap.foliumap as leafmap
from optree import tree_map
from shapely.ops import transform


def shape_3d_to_2d(shape):
    if shape.has_z:
        return transform(lambda x, y, z: (x, y), shape)
    else:
        return shape


def preprocess_gdf(gdf):
    gdf = gdf.to_crs(epsg=7761)  # epsg for Gujarat
    gdf["geometry"] = gdf["geometry"].apply(shape_3d_to_2d)
    gdf["geometry"] = gdf.buffer(0)  # Fixes some invalid geometries
    return gdf


def is_valid_polygon(geometry_gdf):
    geometry = geometry_gdf.geometry.item()
    return (geometry.type == "Polygon") and (not geometry.is_empty)


# wide streamlit display
st.set_page_config(layout="wide")

# Function


# Logo
cols = st.columns([1, 11, 1])
with cols[0]:
    st.image("Final_IITGN-Logo-symmetric-Color.png")
with cols[-1]:
    st.image("IFS.jpg")

# Title
# make title in center
with cols[1]:
    st.markdown(
        f"""
        <h1 style="text-align: center;">KML Viewer</h1>
        """,
        unsafe_allow_html=True,
    )

file_url = st.query_params.get("file_url", None)

if not file_url:
    st.warning(
        "Please provide a KML or GeoJSON URL as a query parameter, e.g., `?file_url=<your_file_url>` or upload a file."
    )
    file_url = st.file_uploader("Upload KML/GeoJSON file", type=["geojson", "kml", "shp"])

if not file_url:
    st.stop()

if ("file_url" in st.session_state) and ("input_gdf" in st.session_state) and (st.session_state.file_url == file_url):
    # st.toast("Using cached data")
    input_gdf = st.session_state.input_gdf
else:
    st.session_state.file_url = file_url
    if isinstance(file_url, str):
        if file_url.startswith("https://drive.google.com/file/d/"):
            ID = file_url.replace("https://drive.google.com/file/d/", "").split("/")[0]
            file_url = f"https://drive.google.com/uc?id={ID}"
        elif file_url.startswith("https://drive.google.com/open?id="):
            ID = file_url.replace("https://drive.google.com/open?id=", "")
            file_url = f"https://drive.google.com/uc?id={ID}"

    input_gdf = preprocess_gdf(gpd.read_file(file_url))
    if len(input_gdf) > 1:
        st.warning(f"Only the first polygon in the KML will be processed; all other geometries will be ignored.")

    for i in range(len(input_gdf)):
        geometry_gdf = input_gdf[input_gdf.index == i]
        if is_valid_polygon(geometry_gdf):
            break
    else:
        st.error(f"No polygon found inside KML. Please check the KML file.")
        st.stop()

    st.session_state.input_gdf = input_gdf
    # st.toast("Data loaded and cached")


def format_fn(x):
    return input_gdf.drop(columns=["geometry"]).loc[x].to_dict()


with st.expander("Advanced Controls", expanded=False):
    # input_geometry_idx = st.selectbox("Select the geometry", input_gdf.index, format_func=format_fn)
    map_type = st.radio(
        "",
        ["Esri Satellite Map", "Google Hybrid Map (displays place names)", "Google Satellite Map"],
        horizontal=True,
    )
    height = st.number_input("Map height (px)", 1, 10000, 600, 1)

geometry_gdf = input_gdf[input_gdf.index == 0]


def check_valid_geometry(geometry_gdf):
    geometry = geometry_gdf.geometry.item()
    if geometry.type != "Polygon":
        st.error(f"Selected geometry is of type '{geometry.type}'. Please provide a 'Polygon' geometry.")
        st.stop()


check_valid_geometry(geometry_gdf)

m = leafmap.Map()

st.markdown(
    """
<style>
.stRadio [role=radiogroup]{
    align-items: center;
    justify-content: center;
}
</style>
""",
    unsafe_allow_html=True,
)

if map_type == "Google Hybrid Map (displays place names)":
    st.write(
        "<h4><div style='text-align: center;'>Google Hybrid (displays place names)</div></h4>",
        unsafe_allow_html=True,
    )
    m.add_basemap("HYBRID")
elif map_type == "Google Satellite Map":
    st.write("<h4><div style='text-align: center;'>Google Satellite</div></h4>", unsafe_allow_html=True)
    m.add_basemap("SATELLITE")
elif map_type == "Esri Satellite Map":
    st.write("<h4><div style='text-align: center;'>Esri - 2024/10/10</div></h4>", unsafe_allow_html=True)
    m.add_wms_layer(
        "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/GoogleMapsCompatible/MapServer/tile/56450/{z}/{y}/{x}",
        layers="0",
    )
else:
    st.error("Invalid map type")
    st.stop()
m.add_gdf(
    geometry_gdf.to_crs(epsg=4326),
    layer_name="Geometry",
    zoom_to_layer=True,
    style_function=lambda x: {"color": "red", "fillOpacity": 0.0},
)
m.to_streamlit(height=height)

# Metrics
stats_df = pd.DataFrame()
stats_df["Points"] = json.loads(geometry_gdf.to_crs(4326).to_json())["features"][0]["geometry"]["coordinates"]
stats_df["Centroid"] = geometry_gdf.centroid.to_crs(4326).item()
stats_df["Area (ha)"] = geometry_gdf.geometry.area.item() / 10000
stats_df["Perimeter (m)"] = geometry_gdf.geometry.length.item()

st.write("<h3><div style='text-align: center;'>Geometry Metrics</div></h3>", unsafe_allow_html=True)
#     st.markdown(
#         f"""| Metric | Value |
# | --- | --- |
# | Area (ha) | {stats_df['Area (ha)'].item():.2f} ha|
# | Perimeter (m) | {stats_df['Perimeter (m)'].item():.2f} m |"""
#     unsafe_allow_html=True)
centroid_lon = stats_df["Centroid"].item().xy[0][0]
centroid_lat = stats_df["Centroid"].item().xy[1][0]
centroid_url = f"http://maps.google.com/maps?q={centroid_lat},{centroid_lon}&layer=satellite"
st.markdown(
    f"""
<div style="display: flex; justify-content: center;">
    <table>
        <tr>
            <th>Metric</th>
            <th>Value</th>
        </tr>
<td>Centroid</td>
<td>
({centroid_lon:.5f}, {centroid_lat:.5f})
    <a href="{centroid_url}" target="_blank">
        <button>View on Google Maps</button>
    </a>
</td>
</tr>
            <td>Area (ha)</td>
            <td>{stats_df['Area (ha)'].item():.2f} ha</td>
        </tr>
        <tr>
            <td>Perimeter (m)</td>
            <td>{stats_df['Perimeter (m)'].item():.2f} m</td>
        </tr>
    </table>
</div>
""",
    unsafe_allow_html=True,
)
print(stats_df["Points"].item())
print(type(stats_df["Points"].item()))

csv = stats_df.T.to_csv(index=True)
st.download_button("Download Geometry Metrics", csv, f"{file_url}_metrics.csv", "text/csv", use_container_width=True)


if isinstance(file_url, str):
    st.markdown(
        f"""
        <div style="display: flex; justify-content: center;">
            <a href="https://huggingface.co/spaces/SustainabilityLabIITGN/NDVI_PERG?file_url={file_url}" target="_blank">
                <button style="
                    background-color: #006400; /* Green background */
                    color: white; /* White text */
                    padding: 10px 20px;
                    font-size: 16px;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                ">
                    Click for NDVI Timeseries
                </button>
            </a>
        </div>
        """,
        unsafe_allow_html=True,
    )
# else:
#     st.markdown(
#         f"""
#         <div style="display: flex; justify-content: center;">
#                 <button style="
#                     background-color: #FF0000; /* Green background */
#                     color: white; /* White text */
#                     padding: 10px 20px;
#                     font-size: 16px;
#                     border: none;
#                     border-radius: 5px;
#                     cursor: pointer;
#                 ">
#                     Click for NDVI Timeseries (This button will be enabled when you provide a file via `?file_url=`)
#                 </button>
#             </a>
#         </div>
#         """,
#         unsafe_allow_html=True,
#     )
