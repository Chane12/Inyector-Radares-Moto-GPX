"""
radares_app.py
===================
Interfaz UI Streamlit para Inyector de Radares.
"""
import streamlit as st
from radares_core import (
    load_gpx_track, simplify_track, get_radares_gdf, 
    intersect_radares_route, inject_waypoints
)

st.set_page_config(
    page_title="Inyector de Radares GPX",
    page_icon="🏍️",
    layout="centered"
)

st.title("🏍️ Inyector de Radares para Moto")
st.markdown(
    "Sube tu ruta GPX. Inyectaremos radares de velocidad "
    "como puntos de paso (waypoints) en el archivo de forma automática."
)

uploaded_file = st.file_uploader("Sube tu archivo .gpx", type=["gpx"])

if uploaded_file is not None:
    with st.spinner("Procesando tu ruta GPX..."):
        try:
            # 1. Cargar datos del GPX y Parsear Track
            gpx_bytes = uploaded_file.getvalue()
            gpx_obj, track_geom = load_gpx_track(gpx_bytes)
            
            # 2. Simplificar traza temporalmente para el motor GIS
            simplified_geom = simplify_track(track_geom)
            
            # 3. Descargar radares en el BBox con caché agresiva
            gdf_radares = get_radares_gdf(simplified_geom)
            
            # 4. Encontrar radares solapados a <30m en UTM 30N
            gdf_radares_ruta = intersect_radares_route(simplified_geom, gdf_radares)
            
            # 5. Inyectar tags al objeto GPX intacto
            gpx_final = inject_waypoints(gpx_obj, gdf_radares_ruta)
            
            # 6. Preparar salida XML
            xml_str = gpx_final.to_xml()
            num_radares = len(gdf_radares_ruta)
            
            st.success(f"¡Proceso completado! Se han inyectado {num_radares} radares sobre la ruta.")
            
            # Botón prominente de descarga sin widgets innecesarios
            file_name = uploaded_file.name.replace(".gpx", "_radares.gpx")
            st.download_button(
                label="📥 Descargar GPX Modificado",
                data=xml_str,
                file_name=file_name,
                mime="application/gpx+xml",
                use_container_width=True
            )

        except Exception as e:
            st.error(f"Ha ocurrido un error procesando el archivo GPX: {e}")
