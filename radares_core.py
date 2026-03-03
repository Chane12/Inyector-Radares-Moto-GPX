"""
radares_core.py
===================
Núcleo GIS paramétrico para la inyección de radares en trazas GPX.

Diseñado con eficiencia O(1) total (Data Lake Local) usando 
Predicate Pushdown sobre GeoParquet.
Cruce geométrico estricto en EPSG:25830 (UTM 30N) y buffer 30m.
"""

from __future__ import annotations
import copy
import math
import warnings
from pathlib import Path

import gpxpy
import gpxpy.gpx
import geopandas as gpd
import pandas as pd
import requests
import streamlit as st
from shapely.geometry import LineString, Point, MultiLineString

# Silencia advertencias de GeoPandas
warnings.filterwarnings("ignore", category=UserWarning, module="geopandas")

# CRS de origen (GPS / WGS84)
CRS_WGS84 = "EPSG:4326"


def load_gpx_track(gpx_path) -> tuple[gpxpy.gpx.GPX, MultiLineString]:
    """
    Lee un archivo GPX (ruta o bytes) y extrae el track principal como un 
    MultiLineString de Shapely iterando sobre los segmentos, y devuelve el objeto GPX
    completo e inofensivo. Previene el 'teletransporte topológico'.
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

    lines = []

    for track in gpx.tracks:
        for segment in track.segments:
            coords = [(point.longitude, point.latitude) for point in segment.points]
            if len(coords) >= 2:
                lines.append(LineString(coords))

    if not lines:
        for route in gpx.routes:
            coords = [(point.longitude, point.latitude) for point in route.points]
            if len(coords) >= 2:
                lines.append(LineString(coords))

    if not lines:
        raise ValueError("El GPX debe contener al menos un segmento con 2 puntos.")

    return gpx, MultiLineString(lines)


def simplify_track(track: MultiLineString, tolerance_deg: float = 0.0001) -> MultiLineString:
    """
    Simplifica un MultiLineString usando el algoritmo de Ramer-Douglas-Peucker.
    Reservado EXCLUSIVAMENTE para visualización. Su uso en cruce de radares
    causa 'Destrucción Topológica' (corta curvas de herradura).
    """
    return track.simplify(tolerance_deg, preserve_topology=True)


@st.cache_data(show_spinner=False, max_entries=5, ttl=3600)
def _read_parquet_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> gpd.GeoDataFrame:
    """
    Lee del archivo .parquet usando Predicate Pushdown (bbox).
    La memoria RAM empleada es marginal y la latencia O(1).
    """
    parquet_path = Path("data/radares_espana.parquet")
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"No se encuentra el Data Lake en {parquet_path}. "
            "Ejecuta 'python scripts/descargar_radares_nacionales.py' primero."
        )
    return gpd.read_parquet(parquet_path, bbox=(min_lon, min_lat, max_lon, max_lat))


def load_local_radares(track: MultiLineString) -> gpd.GeoDataFrame:
    """
    Lee directamente del disco SOLO los radares que caen en el BBox extendido de la ruta.
    Aplica redondeo expansivo matemático al grid absoluto para una caché determinista OOM-proof.
    Proyecta los resultados a CRS Local UTM de forma transparente.
    """
    # 1. Bounding box estricto del track original
    min_x, min_y, max_x, max_y = track.bounds
    
    # Añadimos un pequeño margen de seguridad (~5 km)
    margin = 0.05
    min_x -= margin
    min_y -= margin
    max_x += margin
    max_y += margin
    
    # 2. Redondeo a cuadrícula absoluta (Grid Snapping) de 0.5 grados
    cache_min_lon = math.floor(min_x / 0.5) * 0.5
    cache_min_lat = math.floor(min_y / 0.5) * 0.5
    cache_max_lon = math.ceil(max_x / 0.5) * 0.5
    cache_max_lat = math.ceil(max_y / 0.5) * 0.5
    
    # 3. Predicate Pushdown para lectura O(1) ultra rápida
    gdf_radares_wgs = _read_parquet_bbox(cache_min_lon, cache_min_lat, cache_max_lon, cache_max_lat)
    
    if gdf_radares_wgs.empty:
        # Devolver GDF vacío proyectado
        gdf_track_wgs = gpd.GeoDataFrame(geometry=[track], crs=CRS_WGS84)
        local_crs = gdf_track_wgs.estimate_utm_crs()
        return gpd.GeoDataFrame(columns=["id", "maxspeed", "geometry"], crs=local_crs)
        
    # 4. Estimar CRS Local y proyectar el DataFrame a distancias métricas
    gdf_track_wgs = gpd.GeoDataFrame(geometry=[track], crs=CRS_WGS84)
    local_crs = gdf_track_wgs.estimate_utm_crs()
    
    if gdf_radares_wgs.crs is None:
        gdf_radares_wgs.set_crs(CRS_WGS84, inplace=True)
        
    gdf_radares_utm = gdf_radares_wgs.to_crs(local_crs)
    return gdf_radares_utm


def intersect_radares_route(track: MultiLineString, gdf_radares: gpd.GeoDataFrame, buffer_meters: float = 30.0) -> gpd.GeoDataFrame:
    """
    Cruce Espacial de Alta Precisión:
    Utiliza sjoin_nearest para evitar OOM con buffers poligonales complejos de la ruta.
    Busca radares a menos de buffer_meters mediante matemática vectorial.
    
    IMPORTANTE: El `track` suministrado aquí NUNCA debe ser una geometría simplificada,
    o de lo contrario el atajo matará radares en curvas cerradas.
    """
    if gdf_radares.empty:
        return gdf_radares

    # 1. Estimar CRS Local y proyectar el track original sin simplificar
    gdf_track = gpd.GeoDataFrame(geometry=[track], crs=CRS_WGS84)
    local_crs = gdf_track.estimate_utm_crs()
    gdf_track_utm = gdf_track.to_crs(local_crs)
    
    # Nos aseguramos que los radares vengan en el mismo CRS local (load_local_radares ya lo hace)
    if gdf_radares.crs != local_crs:
        gdf_radares = gdf_radares.to_crs(local_crs)

    # 2. Spatial Join Nearest (distancia máxima de intersección O(1))
    gdf_joined = gpd.sjoin_nearest(
        gdf_radares, 
        gdf_track_utm, 
        how="inner", 
        max_distance=buffer_meters,
        distance_col="dist_ruta"
    )
    
    # 3. Previene radares duplicados teóricos por seguridad
    gdf_joined = gdf_joined.drop_duplicates(subset=["id"])
    
    # 4. Deduplicación Espacial Vectorial y Retención Algorítmica Preventiva (Sin iterrows)
    # Protege al motorista de "Tartamudeos TTS" en radares de doble carril, garantizando 
    # la retención estricta de la velocidad inferior/restrictiva mediante Álgebra de Conjuntos (C-GEOS).
    if len(gdf_joined) > 1:
        # 4.a. Creación Vectorial de la Topología de Colapso (Radio 25m = Tolerancia 50m)
        buffers = gdf_joined.geometry.buffer(25)
        union_geom = buffers.unary_union
        
        if union_geom.geom_type == 'Polygon':
            clusters = [union_geom]
        elif union_geom.geom_type == 'MultiPolygon':
            clusters = list(union_geom.geoms)
        else:
            clusters = []
            
        gdf_clusters = gpd.GeoDataFrame({"cluster_id": range(len(clusters))}, geometry=clusters, crs=local_crs)
        
        # 4.b. Spatial Join Nativo: Inscribe cada radar orgánico en su clúster de contención
        gdf_clustered = gpd.sjoin(gdf_joined, gdf_clusters, how="inner", predicate="intersects")
        
        # 4.c. Álgebra Relacional: Extraer velocidad restrictiva global dentro del clúster (O(N) nativo)
        gdf_clustered["speed_num"] = pd.to_numeric(gdf_clustered["maxspeed"], errors="coerce")
        min_speeds = gdf_clustered.groupby("cluster_id")["speed_num"].min()
        
        # 4.d. Consolidación Geoespacial y Proyección de Atributos
        # Retenemos un único radar representativo por cada macro-clúster (eliminando las ramas urbanas inútiles)
        gdf_joined = gdf_clustered.drop_duplicates(subset=["cluster_id"]).copy()
        
        # Auto-mapeamos la velocidad restrictiva absoluta calculada al 'waypoint' representativo
        gdf_joined["speed_num"] = gdf_joined["cluster_id"].map(min_speeds)
        
        # Inyectar el número en string al 'maxspeed' conservando los nulos (None/NaN) de forma segura
        mask = gdf_joined["speed_num"].notna()
        gdf_joined.loc[mask, "maxspeed"] = gdf_joined.loc[mask, "speed_num"].astype(int).astype(str)
        
        # Limpieza simétrica de metadata temporal de la tabla
        cols_to_keep = [col for col in gdf_joined.columns if col not in ['index_right', 'cluster_id', 'speed_num']]
        gdf_joined = gdf_joined[cols_to_keep]

    return gdf_joined


def inject_waypoints(gpx: gpxpy.gpx.GPX, gdf_radares: gpd.GeoDataFrame) -> gpxpy.gpx.GPX:
    """
    Añade nodos <wpt> al objeto GPX para cada radar en ruta.
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
