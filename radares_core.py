"""
radares_core.py
===================
Núcleo GIS paramétrico para la inyección de radares en trazas GPX.

Diseñado con eficiencia O(1) en red espacial mediante descarga de 
Bounding Box y caché agresiva con Streamlit.
Cruce geométrico en EPSG:25830 (UTM 30N) usando buffer de 30m e indexación R-Tree.
"""

from __future__ import annotations
import copy
import warnings
from pathlib import Path

import gpxpy
import gpxpy.gpx
import geopandas as gpd
import pandas as pd
import requests
import streamlit as st
from shapely.geometry import LineString, Point

# Silencia advertencias de GeoPandas
warnings.filterwarnings("ignore", category=UserWarning, module="geopandas")

# CRS de origen (GPS / WGS84) y CRS de trabajo (UTM zona 30N, metro como unidad)
CRS_WGS84 = "EPSG:4326"
CRS_UTM30N = "EPSG:25830"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def load_gpx_track(gpx_path) -> tuple[gpxpy.gpx.GPX, LineString]:
    """
    Lee un archivo GPX (ruta o bytes) y extrae el track principal como un 
    LineString de Shapely iterando sobre los segmentos, y devuelve el objeto GPX
    completo e inofensivo.
    """
    if isinstance(gpx_path, bytes):
        try:
            gpx_str = gpx_path.decode("utf-8")
        except UnicodeDecodeError:
            gpx_str = gpx_path.decode("latin-1")
        gpx = gpxpy.parse(gpx_str)
    else:
        gpx_path = Path(gpx_path)
        try:
            with open(gpx_path, "r", encoding="utf-8") as f:
                gpx = gpxpy.parse(f)
        except UnicodeDecodeError:
            with open(gpx_path, "r", encoding="latin-1") as f:
                gpx = gpxpy.parse(f)

    coords: list[tuple[float, float]] = []

    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                coords.append((point.longitude, point.latitude))

    if not coords:
        for route in gpx.routes:
            for point in route.points:
                coords.append((point.longitude, point.latitude))

    if len(coords) < 2:
        raise ValueError("El GPX debe contener al menos 2 puntos.")

    return gpx, LineString(coords)


def simplify_track(track: LineString, tolerance_deg: float = 0.0001) -> LineString:
    """
    Simplifica un LineString usando el algoritmo de Ramer-Douglas-Peucker.
    """
    return track.simplify(tolerance_deg, preserve_topology=True)


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_speed_cameras(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict:
    """
    Realiza una consulta [out:json] a la API de Overpass buscando nodos con 
    la etiqueta highway=speed_camera dentro del BBox.
    """
    query = f"""
    [out:json][timeout:25];
    node["highway"="speed_camera"]({min_lat},{min_lon},{max_lat},{max_lon});
    out body;
    """
    resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_radares_gdf(track: LineString) -> gpd.GeoDataFrame:
    """
    Descarga los radares del bounding box de la ruta y los convierte a un GeoDataFrame.
    Proyecta las coordenadas a EPSG:25830 (UTM 30N).
    """
    # 1. Bounding box con margen paramétrico para evitar omisiones en los extremos
    min_lon, min_lat, max_lon, max_lat = track.bounds
    margin = 0.02  # Aproximadamente 2 km
    min_lon -= margin
    min_lat -= margin
    max_lon += margin
    max_lat += margin

    # 2. Extracción (cacheada @ 24h)
    data = fetch_speed_cameras(min_lon, min_lat, max_lon, max_lat)
    
    elements = data.get("elements", [])
    if not elements:
        return gpd.GeoDataFrame(columns=["id", "maxspeed", "geometry"], crs=CRS_UTM30N)

    # 3. Construir lista de puntos
    records = []
    geometry = []
    for el in elements:
        lon, lat = el.get("lon"), el.get("lat")
        if lon is None or lat is None:
            continue
        tags = el.get("tags", {})
        records.append({
            "id": el.get("id"),
            "maxspeed": tags.get("maxspeed", None)
        })
        geometry.append(Point(lon, lat))

    if not geometry:
        return gpd.GeoDataFrame(columns=["id", "maxspeed", "geometry"], crs=CRS_UTM30N)

    # 4. Crear GDF WGS84 y proyectar a UTM30N
    gdf = gpd.GeoDataFrame(records, geometry=geometry, crs=CRS_WGS84)
    gdf_utm = gdf.to_crs(CRS_UTM30N)
    
    return gdf_utm


def intersect_radares_route(track: LineString, gdf_radares: gpd.GeoDataFrame, buffer_meters: float = 30.0) -> gpd.GeoDataFrame:
    """
    Cruce Espacial de Alta Precisión:
    Crea un buffer de 30 metros alrededor de la ruta en UTM 30N.
    Utiliza gpd.sjoin con el motor de indexación R-Tree e 'intersects'.
    """
    if gdf_radares.empty:
        return gdf_radares

    # 1. Proyectar el track en WGS84 a UTM 30N
    gdf_track = gpd.GeoDataFrame(geometry=[track], crs=CRS_WGS84)
    gdf_track_utm = gdf_track.to_crs(CRS_UTM30N)

    # 2. Buffer de 30 metros
    gdf_buffer = gdf_track_utm.copy()
    gdf_buffer["geometry"] = gdf_track_utm.buffer(buffer_meters, resolution=3)

    # 3. Spatial Join
    gdf_joined = gpd.sjoin(
        gdf_radares, 
        gdf_buffer[["geometry"]], 
        how="inner", 
        predicate="intersects"
    )
    
    # Previene radares duplicados si múltiples secciones de ruta hacen intersección
    gdf_joined = gdf_joined.drop_duplicates(subset=["id"])
    return gdf_joined


def inject_waypoints(gpx: gpxpy.gpx.GPX, gdf_radares: gpd.GeoDataFrame) -> gpxpy.gpx.GPX:
    """
    Añade nodos <wpt> al objeto GPX para cada radar en ruta.
    
    Esquema de Etiquetas:
    - <name>: "RADAR [Valor]" o "RADAR FIJO"
    - <sym>: "Danger"
    - <desc>: Mensaje estándar de aviso preventivo.
    """
    gpx_out = copy.deepcopy(gpx)
    
    if not gdf_radares.empty:
        # Volver al CRS original para inscribir coordenadas lógicas en el GPX
        gdf_radares_wgs = gdf_radares.to_crs(CRS_WGS84)
        
        for idx, row in gdf_radares_wgs.iterrows():
            lon = row.geometry.x
            lat = row.geometry.y
            maxspeed = row["maxspeed"]
            
            # Procesamiento de Name
            name = "RADAR FIJO"
            if maxspeed and str(maxspeed).isdigit():
                name = f"RADAR {maxspeed}"
                
            wpt = gpxpy.gpx.GPXWaypoint(
                latitude=lat, 
                longitude=lon,
                name=name,
                symbol="Danger",
                description="Aviso de radar de velocidad. Reduzca la velocidad y extreme la precaución."
            )
            gpx_out.waypoints.append(wpt)
            
    return gpx_out
