# 🏍️ Inyector de Radares GPX para Moto (Cloud Native Edition)

**Prueba la herramienta en vivo aquí:** [https://chane12-inyector-radares-moto-gpx-radares-app-hkqbrb.streamlit.app/](https://chane12-inyector-radares-moto-gpx-radares-app-hkqbrb.streamlit.app/)

Una arquitectura *Cloud Native* diseñada para resolver un problema crítico del mundo real de forma tolerante a fallos, ultrarrápida y libre de dependencias pesadas. Este sistema ingiere rutas GPX de motociclistas de aventura y enriquece espacialmente el archivo inyectando radares de velocidad como *waypoints*, garantizando su compatibilidad en la navegación offline (OsmAnd, Garmin, DMD2).

Más que una simple utilidad, este proyecto es un ejercicio de **Ingeniería de Sistemas, Optimización Algorítmica y Rugged UX**, pensado para ofrecer rendimiento de grado corporativo procesando datos espaciales masivos en contenedores efímeros de bajos recursos.

---

## 🏛️ System Architecture & Data Engineering

El proyecto abandona las llamadas REST en tiempo de ejecución (APIs costosas) en favor de una arquitectura O(1) apoyada en un **Data Lake Local** y matemáticas puras (C-GEOS).

1. **Topología Inofensiva (MultiLineString):** El sistema decodifica el árbol XML del `.gpx` y aísla los segmentos discontinuos generados por cortes de señal de GPS en instancias de `MultiLineString`. Esto previene el clásico bug de "teletransporte", asegurando que jamás se inyecten radares falsos cruzando líneas rectas inventadas sobre el mapa.
2. **Data Lake (GeoParquet) & Predicate Pushdown:** Todos los radares nacionales se pre-empaquetan en un archivo de compresión columnar ultraligera (`data/radares_espana.parquet`). Usando *Predicate Pushdown* espacial (BBox), la aplicación consume cero memoria extra aislando únicamente la región de lectura antes de subir el binario a RAM.
3. **Caché por Malla Cartográfica Absoluta:** Para salvar posibles fugas *Out-Of-Memory* (OOM) provocadas por peticiones web dispars, la geometría se ajusta algorítmicamente mediante *Grid Snapping* de $0.5^\circ$. Múltiples usuarios por la misma región colapsan el estado de memoria hitando la misma sub-cuadrícula global.
4. **Motor Vectorial C-GEOS Estricto:** La intersección prescinde de los polígonos asimétricos masivos (buffers topológicos) ahorrando cálculos O(N²), mutando todo a búsquedas sobre R-Tree con `gpd.sjoin_nearest`. Latencia en milisegundos.
5. **Deduplicación Agresiva (*Greedy Clustering*):** Evita el "spam" en motores de Text-To-Speech iterando sobre clústeres nativos construidos relacionalmente a través de `unary_union`. En escenarios de radares desdoblados en la misma calzada, la CPU asegura agrupar el clúster conservando la restricción legal más baja.

---

## 🛡️ CI/CD: The "Sanity" Wall

El Data Lake se alimenta asíncronamente vía un cronjob mensual en Github Actions que extrae información de la API de OpenStreetMap (Overpass).  
Para evitar la **Degradación Silenciosa**, la automatización debe superar 3 Sanity Checks estadísticos antes de fusionar en `main`:

- **Densidad Volumétrica**: Freno antinidos (Abortar si hay menos de $2800$ radares).
- **Proporción Espacial**: Fallo ante Rate Limits (Verifica las amplitudes de caja Lat/Lon de todo el país).
- **Integridad Semántica**: Cierre de válvulas si los metadatos caen (se exige ratio mínimo del 20% en `maxspeed`).

Un sistema de interbloqueo con *Crashes* limpios (`sys.exit(1)`) descarta Auto-Commits envenenados que tumben el servicio en producción de forma sorda y sin levantar alarmas.

---

## 📲 Rugged UX (Diseño hostil)

La experiencia de la interfaz Streamlit se ha mutado específicamente en condiciones de movilidad extrema para motoristas:

- **State Blindado:** Al girar el dispositivo, perder conexión a la red intermitentemente o navegar entre menús, tu flujo persiste gracias al sellado de `st.session_state`.
- **Feedbacks Psicológicos Inmediatos:** Componentes granulares como `st.status` informan dinámicamente al piloto en tiempo real de los picos de procesamiento y logrando la anulación visual del temido "cuélgue del spinner en gris".
- **Botones y Touch Targets Adaptativos:** Inyección de CSS estricta para redimensionar los inputs/outputs de modo mastodóntico para interacción efectiva portando guantes de cuero.

---

## 🛠️ Despliegue Local & Ejecución

El código puede orquestarse y lanzarse siguiendo este flujo:

**1. Clonar e Instalar Setup Virtual:**

```bash
git clone https://github.com/Chane12/Inyector-Radares-Moto-GPX.git
cd Inyector-Radares-Moto-GPX

python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

**2. Poblar el Data Lake Asíncrono (Si ejecutas tu propia acción manual):**

```bash
python scripts/descargar_radares_nacionales.py
```

**3. Activar el Motor de Combustión UI (Streamlit):**

```bash
streamlit run radares_app.py
```
