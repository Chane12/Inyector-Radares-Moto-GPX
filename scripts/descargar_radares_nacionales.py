"""
scripts/descargar_radares_nacionales.py
=======================================
Script independiente (Data Lake Builder) para descargar de un golpe todos los radares de 
la Península Ibérica/país objetivo mediante Overpass API y guardarlos en GeoParquet.
Diseñado para su uso asíncrono (ej. CRON semanal) y proporcionar O(1) al cliente final.
"""

import os
import requests
import geopandas as gpd
from shapely.geometry import Point

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

def descargar_radares_bbox(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> gpd.GeoDataFrame | None:
    print(f"Descargando radares para BBox ({min_lon}, {min_lat}, {max_lon}, {max_lat})...")
    query = f"""
    [out:json][timeout:300];
    node["highway"="speed_camera"]({min_lat},{min_lon},{max_lat},{max_lon});
    out body;
    """
    headers = {
        "User-Agent": "RadaresGPXOptimizer/1.0 DataLake Builder"
    }

    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"Error de red accediendo a Overpass API: {e}")
        return None
    
    elements = data.get("elements", [])
    print(f"Descargados {len(elements)} radares de OSM.")
    
    records = []
    geometries = []
    
    for el in elements:
        lon, lat = el.get("lon"), el.get("lat")
        if lon is None or lat is None:
            continue
            
        tags = el.get("tags", {})
        records.append({
            "id": str(el.get("id")),
            "maxspeed": tags.get("maxspeed", None)
        })
        geometries.append(Point(lon, lat))

    if not records:
        print("No se encontraron radares en este BBox.")
        return None

    gdf = gpd.GeoDataFrame(records, geometry=geometries, crs="EPSG:4326")
    return gdf

if __name__ == "__main__":
    print("Iniciando construcción del Data Lake de radares...")
    
    # BBox de la Península Ibérica + Sur de Francia (aprox)
    # min_lon, min_lat, max_lon, max_lat
    PENINSULA_BBOX = (-9.5, 36.0, 4.0, 44.0)
    
    gdf_radares = descargar_radares_bbox(*PENINSULA_BBOX)
    
    if gdf_radares is not None:
        os.makedirs("data", exist_ok=True)
        out_path = "data/radares_espana.parquet"
        print(f"Guardando {len(gdf_radares)} radares en {out_path} mediante formato columnar...")
        gdf_radares.to_parquet(out_path, index=False, schema_version="1.1.0", write_covering_bbox=True)
        print("¡Data Lake construido con éxito! 🚀")
