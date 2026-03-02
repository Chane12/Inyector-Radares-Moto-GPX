# 🏍️ Inyector de Radares GPX para Moto

Una herramienta autónoma, ultrarrápida y libre de dependencias complejas diseñada específicamente para motociclistas de aventura. Permite inyectar de forma inteligente radares de velocidad como *waypoints* (Puntos de Paso) en cualquier archivo `.gpx` existente, garantizando total compatibilidad con navegadores offline líderes como **OsmAnd**, **Garmin** o **DMD2**.

---

## 🏛️ System Architecture

El sistema abandona por completo los motores de enrutamiento pesado (OSRM) en favor de una arquitectura espacial ligera **$\mathcal{O}(1)$ en latencia de red**:

1. **Ingestión GPX Inofensiva:** Se analiza el archivo `.gpx` del usuario de forma no destructiva, aislando la geometría topológica base sin mutilar metadatos preexistentes.
2. **Consultas Bounding Box (BBox):** Se calcula el BBox envolvente de la ruta y se lanza una consulta directa a la API de **Overpass (OpenStreetMap)** buscando *exclusivamente* nodos etiquetados como `highway=speed_camera`.
3. **Caché Agresiva `@st.cache_data`:** Los nodos de la zona se almacenan en RAM por 24 horas, anulando peticiones redundantes cuando iteramos variaciones del mismo track.
4. **Cruce Espacial O(log n):** Volcado de memoria en Geometría Métrica EPSG:25830 (UTM 30N) aplicando un buffer de solape ajustado a 30 metros de tolerancia en carretera.
5. **Inyección de Waypoints TTS:** Inserción limpia dentro de la metadata del track con etiquetado semántico `<sym>Danger</sym>` para detonar el motor Text-To-Speech del dispositivo en ruta.

---

## 💻 Tech Stack & Dependencies

Stack aligerado y estandarizado con un footprint base de memoria ínfimo.

| Componente                | Stack Principal                  | Racional Técnico                                                                         |
|---------------------------|----------------------------------|------------------------------------------------------------------------------------------|
| **Core GIS Espacial**     | `geopandas`, `shapely`           | Cruce y análisis métrico Vectorial con soporte SRID UTM. Motor analítico GEOS R-Tree.    |
| **Ingesta OpenStreetMap** | `requests`, *Overpass API*       | Ingesta granular de nodos por caja delimitadora (BBox) eliminando grafos iterativos.     |
| **GPX Manipulator**       | `gpxpy`                          | Serialización XML de la capa superior manteniendo la integridad de los Tracks/Rutas.     |
| **Frontend Minimalista**  | `streamlit`                      | Control de estado simple con componente `file_uploader` para un UX vertical asíncrono.   |

---

## 🛠️ Despliegue Local

El repositorio es modular y la configuración un simple proceso en tres pasos:

**1. Clonar el repositorio y acceder:**

```bash
git clone https://github.com/Chane12/Gasolineras-GPX-Optimizador-de-Repostaje-en-Ruta.git
cd Gasolineras-GPX-Optimizador-de-Repostaje-en-Ruta
```

**2. Entorno Virtual y Dependencias:**

```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

**3. Ejecución Interfaz Streamlit:**

```bash
streamlit run radares_app.py
```
