# 🏍️ Inyector de Radares GPX para Moto

Una herramienta autónoma, ultrarrápida y libre de dependencias complejas diseñada específicamente para motociclistas de aventura. Permite inyectar de forma inteligente radares de velocidad como *waypoints* (Puntos de Paso) en cualquier archivo `.gpx` existente, garantizando total compatibilidad con navegadores offline líderes como **OsmAnd**, **Garmin** o **DMD2**.

---

## 🏛️ System Architecture

El sistema abandona por completo los costosos motores de red o APIs externas iterativas en favor de una **arquitectura espacial offline $\mathcal{O}(1)$ de latencia**, implementando un Data Lake local optimizado:

1. **Ingestión GPX Desacoplada y No Destructiva:** Se analiza y decodifica el árbol XML del archivo `.gpx` aislando la geometría topológica base sin mutilar metadatos preexistentes.
2. **Data Lake en GeoParquet & Predicate Pushdown:** Consulta directa sobre un dataset local (`data/radares_espana.parquet`) utilizando *Predicate Pushdown* (BBox espacial) a nivel de I/O. Esto descarta la lectura de memoria de datos fuera del scope perimetral de la ruta, logrando acceso $\mathcal{O}(1)$ escalable e idóneo para hardware de bajos recursos.
3. **Caché Espacial Determinista `@st.cache_data`:** Expansión topológica de celda a nivel matemático (cuadrícula flotante) para garantizar una carga RAM *OOM-proof*, permitiendo recargar la misma área sin golpear el sistema de I/O reiteradamente.
4. **Cruce Espacial R-Tree ($\mathcal{O}(\log N)$):** Sistema de intersecciones métricas exactas vectorizado por `geopandas`. El sistema hace una inferencia y proyección automática de CRS (e.g., *EPSG:25830 / UTM 30N*) para generar buffers diametrales de 30 metros paramétricos, impidiendo cortes algorítmicos al no simplificar el trazado matriz.
5. **Inyección de Waypoints Semánticos TTS:** Reempaquetado del *GPX Object* para instanciar `<wpt>` con etiquetas de semántica `<sym>Danger</sym>`, ideados formalmente para gatillar los motores *Text-To-Speech* de navegadores offline.

---

## 💻 Tech Stack & Dependencies

Stack aligerado y estandarizado, focalizado en alto rendimiento de procesamiento de datos espaciales.

| Componente                    | Stack Principal                  | Racional Técnico                                                                         |
|-------------------------------|----------------------------------|------------------------------------------------------------------------------------------|
| **Core Geométrico & Análisis**| `geopandas`, `shapely`           | Análisis Vectorial métrico paramétrico con inferencia UTM. Indexación Espacial R-Tree.   |
| **Motor I/O Data Lake**       | `parquet` (pyarrow)              | Almacenamiento columnar comprimido; lectura vectorizada vía *Predicate Pushdown*.        |
| **GPX Manipulator**           | `gpxpy`                          | Serialización XML de alto nivel manteniendo integridad paramétrica de los *Tracks*.      |
| **Frontend Asíncrono**        | `streamlit`                      | Control de estado simple con componente visual inmersivo para un UX de fricción cero.    |

---

## 🛠️ Despliegue Local

El repositorio es modular y la configuración un simple proceso local:

**1. Clonar el repositorio:**

```bash
git clone https://github.com/Chane12/Inyector-Radares-Moto-GPX.git
cd Inyector-Radares-Moto-GPX
```

**2. Entorno Virtual e Instalación de Dependencias:**

```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

**3. Precarga del Data Lake Local (Radares España):**

```bash
python scripts/descargar_radares_nacionales.py
```

**4. Ejecución del Core en Streamlit:**

```bash
streamlit run radares_app.py
```
