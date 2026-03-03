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
    
    import sys
    
    gdf_radares = descargar_radares_bbox(*PENINSULA_BBOX)
    
    if gdf_radares is None:
        print("❌ ERROR CRÍTICO: La extracción ha devuelto None (fallo de red o sin datos).", file=sys.stderr)
        print("Abortando GitHub Action con código 1 para prevenir Degradación Silenciosa y auto-commit destructivo.", file=sys.stderr)
        sys.exit(1)
        
    if gdf_radares is not None:
        # =================================================================
        # SANITY CHECKS (AUDITORÍA DE CALIDAD ANTI-ENVENENAMIENTO)
        # =================================================================
        print("Iniciando auditoría de calidad (Sanity Checks)...")
        
        # 1. Validación de Volumen Mínimo (Estadística)
        # Históricamente sabemos que hay más de 3000 radares.
        MIN_RADARES_ESPERADOS = 2800
        total_radares = len(gdf_radares)
        if total_radares < MIN_RADARES_ESPERADOS:
            raise ValueError(f"SANITY CHECK FALLIDO: Volumen crítico bajo. "
                             f"Apenas {total_radares} radares detectados frente a los {MIN_RADARES_ESPERADOS} esperados. "
                             "Posible anomalía o microcorte en Overpass API.")
                             
        # 2. Validación Espacial / Dispersión (Geométrica)
        # Verificamos que los puntos realmente cubren la geografía ibérica y no son solo un clúster local 
        # fruto de un Rate Limit que cortó la request por la mitad.
        minx, miny, maxx, maxy = gdf_radares.total_bounds
        amplitud_lon = maxx - minx
        amplitud_lat = maxy - miny
        
        if amplitud_lon < 10.0 or amplitud_lat < 5.0:
            raise ValueError(f"SANITY CHECK FALLIDO: Colapso espacial. "
                             f"La caja delimitadora resultantes es anormalmente pequeña (Lon: {amplitud_lon:.1f}º, Lat: {amplitud_lat:.1f}º). "
                             "La API ha devuelto un resultado parcial.")
                             
        # 3. Integridad Atributiva Crítica
        # Asegurar que una masa razonable de radares (ej. al menos un 30%) tenga etiqueta de velocidad máxima.
        # Si de repente todos pierden la velocidad, la estructura semántica ha cambiado o fallado.
        con_velocidad = gdf_radares['maxspeed'].notna().sum()
        ratio_velocidad = con_velocidad / total_radares
        if ratio_velocidad < 0.20:
            raise ValueError(f"SANITY CHECK FALLIDO: Atributos corruptos. "
                             f"Apenas el {ratio_velocidad*100:.1f}% de radares tiene etiqueta 'maxspeed'. "
                             "Anomalía en los metadatos de OpenStreetMap.")
                             
        print("✅ Auditoría superada: Volumen, Dispersión Espacial e Integridad validados.")
        # =================================================================
        
        os.makedirs("data", exist_ok=True)
        out_path = "data/radares_espana.parquet"
        print(f"Guardando {total_radares} radares en {out_path} mediante formato columnar...")
        gdf_radares.to_parquet(out_path, index=False, schema_version="1.1.0", write_covering_bbox=True)
        print("¡Data Lake construido con éxito! 🚀")
