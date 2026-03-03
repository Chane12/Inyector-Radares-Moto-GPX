"""
radares_app.py
===================
Interfaz UI Streamlit para Inyector de Radares.
"""
import streamlit as st
from radares_core import (
    load_gpx_track, load_local_radares, 
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

# 0. Instanciación del Estado Mutante (session_state)
if 'processed_gpx' not in st.session_state:
    st.session_state.processed_gpx = None
if 'radar_count' not in st.session_state:
    st.session_state.radar_count = 0
if 'last_file_id' not in st.session_state:
    st.session_state.last_file_id = None

uploaded_file = st.file_uploader("Sube tu archivo .gpx", type=["gpx"])

# 1. Pipeline de Procesamiento asimétrico persistente
if uploaded_file and uploaded_file.file_id != st.session_state.last_file_id:
    # Resetea y guarda el hash del nuevo archivo
    st.session_state.processed_gpx = None
    st.session_state.last_file_id = uploaded_file.file_id
    
    with st.status("Analizando tu ruta...", expanded=True) as status:
        try:
            st.write("📡 Parseando segmentos topológicos del GPX...")
            gpx_bytes = uploaded_file.getvalue()
            gpx_obj, track_geom = load_gpx_track(gpx_bytes)
            
            st.write("🗺️ Mapeando radares hiperlocales en memoria O(1)...")
            gdf_radares = load_local_radares(track_geom)
            
            st.write("⚡ Ejecutando álgebra de colisión y deduplicación...")
            gdf_radares_ruta = intersect_radares_route(track_geom, gdf_radares)
            
            st.write("💉 Inyectando Waypoints en el track original...")
            gpx_final = inject_waypoints(gpx_obj, gdf_radares_ruta)
            
            # Anclamos la victoria al Estado de Sesión Permanente
            st.session_state.processed_gpx = gpx_final.to_xml()
            st.session_state.radar_count = len(gdf_radares_ruta)
            
            status.update(label="¡Ruta blindada y lista!", state="complete", expanded=False)
            
        except ValueError as e:
            # Captura errores geolocalizados: Rutas sin puntos, etc.
            status.update(label="GPX Inválido o vacío", state="error", expanded=True)
            st.error(f"Revisa tu archivo: {str(e)}")
            st.stop()
        except Exception: 
            # Nunca escupimos el traceback en Producción
            status.update(label="Fallo Crítico al Parsear", state="error", expanded=True)
            st.error("El archivo cargado está corrupto o no cumple el estándar XML/GPX válido.")
            st.stop()

# 2. Renderizado Condicional del Resultado Blindado (Success State)
if st.session_state.processed_gpx:
    st.divider()
    
    # 2.1. st.metrics: Recompensa Psicológica Inmediata
    col1, col2 = st.columns(2)
    col1.metric("📍 Radares Inyectados", st.session_state.radar_count, "Trampas evitadas", delta_color="normal")
    col2.metric("💾 Formato", "GPX XML", "Válido y nativo")
    
    # 2.2. Touch Targets Mastodónticos e Inyección de CSS (Guantes de Moto)
    st.markdown("""
    <style>
        /* Engordamos los botones nativos de Streamlit para guantes */
        div.stDownloadButton > button {
            height: 4rem;
            border-radius: 12px;
            font-size: 1.2rem !important;
            font-weight: 700;
            background-color: #FF4B4B; 
            border: none;
            box-shadow: 0px 4px 10px rgba(255, 75, 75, 0.4);
            transition: transform 0.1s ease;
        }
        div.stDownloadButton > button:active {
            transform: scale(0.95);
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Botón prominente de descarga sin widgets innecesarios
    if uploaded_file:
        file_name = uploaded_file.name.replace(".gpx", "_radares.gpx")
    else:
        file_name = "ruta_radares.gpx"
        
    st.download_button(
        label="🚀 DESCARGAR RUTA BLINDADA",
        data=st.session_state.processed_gpx,
        file_name=file_name,
        mime="application/gpx+xml",
        use_container_width=True
    )
