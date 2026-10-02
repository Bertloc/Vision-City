# Visión City

Prototipo académico de visión artificial para detectar, rastrear y contar cruces de vehículos y peatones en video con Python, OpenCV, Ultralytics YOLO11n y ByteTrack.

> Estado: prueba de concepto operable con resultados preliminares. Los cruces aún deben compararse con anotación manual antes de considerarse validados.

## Alcance

El programa trabaja con las clases persona, bicicleta, automóvil, motocicleta, autobús y camión. Genera un video anotado, un CSV por fotograma y un resumen JSON. No controla semáforos ni incluye dashboards, reconocimiento de placas o entrenamiento de modelos.

## Requisitos

- Windows 10/11 y Python 3.13.
- `ultralytics`, `opencv-python`, `torch` y `lap`.
- CPU o CUDA; se probó en una NVIDIA GeForce GTX 1660 SUPER.

## Instalación

```powershell
git clone https://github.com/Bertloc/Vision-City.git
cd Vision-City
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Los pesos `.pt`, videos y resultados se mantienen fuera de Git. Coloca el video localmente en `data/videos/` y ejecuta:

```powershell
python app.py --source .\data\videos\trafico_cruce.mp4 --config .\config\intersection.json
```

`--show` abre una vista durante el procesamiento y es opcional. `--model` y `--conf` reemplazan los valores de la configuración cuando se proporcionan. Consulta todas las opciones con `python app.py --help`.

## Conteo por líneas

`config/intersection.json` define líneas mediante puntos normalizados `[x, y]`, clases permitidas, nombres de dirección e histéresis. La orientación va de `start` a `end`: un cruce hacia el lado positivo usa `directions.positive` y el contrario usa `directions.negative`.

Para cada ID rastreado se conserva un historial corto del centro de su caja. Un cruce solo se registra cuando el centro sale de la banda de histéresis en el lado opuesto y la trayectoria intersecta el segmento finito. La primera observación no cuenta y cada ID cuenta como máximo una vez por línea.

Las posiciones incluidas son preliminares. Se deben calibrar para el encuadre de cada cámara y validar contra conteo manual.

## Métricas y salidas

### Presencia por zonas y memoria

El flujo adicional es `YOLO → ByteTrack → centro inferior → zonas → TrafficState → TrafficMemory`.
`traffic_state.py` calcula la ocupación actual; `traffic_memory.py` guarda hasta 30 muestras,
una por segundo, y expulsa las de hace 30 segundos o más. No decide semáforos.

Configura `waiting_zones` en `config/intersection.json`. Se entrega vacío porque aún no hay
zonas de espera calibradas. Sin zonas, el programa conserva los cruces y genera estados con
`vehicles_by_zone: {}` y `total_vehicles: 0`.

Para un video nuevo:

1. Abre un fotograma y localiza la superficie de cada carril donde quieres medir presencia.
2. Anota los vértices del polígono en orden alrededor del contorno, sin cruzar aristas,
   sin repetir el primer punto al final y con al menos tres puntos distintos.
3. Divide cada coordenada en píxeles por el ancho o alto: `[x / ancho, y / alto]`.
4. Añade un ID único y un nombre descriptivo. Revisa visualmente el contorno en el video anotado.

Ejemplo **ilustrativo, no calibrado para el clip incluido**:

```json
"waiting_zones": [
  {
    "id": "carril_a",
    "name": "Carril A",
    "points": [[0.10, 0.10], [0.40, 0.10], [0.40, 0.40], [0.10, 0.40]]
  }
]
```

La normalización conserva las zonas al cambiar resolución con el mismo encuadre; un recorte,
cambio de perspectiva o cámara requiere recalibrar. No se deducen puntos cardinales del video.
El punto usado es `((x1 + x2) / 2, y2)`: aproxima el contacto con el pavimento mejor que el centro
de la carrocería. El borde del polígono cuenta como interior. Solo participan car, motorcycle,
bus y truck con `track_id`; peatones y bicicletas mantienen únicamente su comportamiento previo.

Los IDs se deduplican por frame. La ocupación se recalcula desde cero: al salir o dejar de ser
observado, el vehículo desaparece del conteo. No se infiere que esté detenido ni su tiempo de
espera. Una oclusión puede causar subconteo. En zonas solapadas un ID puede aparecer en ambas;
`total_vehicles` cuenta IDs únicos en la unión de zonas, no todos los vehículos del encuadre.
Evita solapamientos si los carriles deben ser exclusivos.

`TrafficState` es una dataclass con `timestamp`, `vehicles_by_zone` y `total_vehicles`.
Se pueden añadir campos opcionales después, como `waiting_time`, `queue_growth`,
`pedestrians_waiting`, `unusual_events` y `confidence`, cuando exista una medición definida.
El video muestra conteos actuales por frame; la consola y el archivo `*_trafico.jsonl` muestran
la primera observación de cada segundo, empezando en t=0. En archivos, el reloj es
`índice_frame / FPS` (supone FPS constante; si no está disponible usa 30 FPS); en cámara es
el tiempo monotónico transcurrido. La inferencia lenta no cambia el reloj del video.
No se rellenan segundos sin observaciones con datos inventados.

Cada línea JSONL contiene una muestra. El resumen JSON añade `traffic_memory` con las últimas
30 muestras como máximo y `waiting_zones` para interpretar sus IDs. El archivo JSONL conserva
todas las muestras en disco; la memoria en ejecución está limitada. Los cruces siguen separados.

Prueba desde la raíz, después de configurar las zonas:

```powershell
.\.venv\Scripts\python.exe app.py --source .\data\videos\trafico_cruce.mp4 --config .\config\intersection.json --output .\output\prueba_cerebro
.\.venv\Scripts\python.exe -m unittest -v
```

Agrega `--show` si quieres una ventana. Observa los polígonos cian con `presentes`, los estados
por segundo en consola y el JSONL, además del MP4, CSV y resumen existentes. Los números
dependen del video, la configuración y las detecciones; no hay un conteo esperado prefijado.

### Análisis y prioridad explicable

`traffic_analysis.py` consume el estado actual, `memory.states` y los IDs de zonas configuradas.
`traffic_priority.py` calcula un `PriorityScore` por zona y un resultado con `winner`, `reason`
y `scores`. Ambos módulos se prueban con estados ficticios sin ejecutar ni importar YOLO.
No agrupan zonas en fases ni calculan tiempos verdes.

Parámetros en `config/intersection.json` (las configuraciones antiguas usan estos valores por defecto):

```json
"traffic_analysis": {
  "window_seconds": 8.0,
  "min_samples": 3,
  "trend_threshold": 0.1
},
"traffic_priority": {
  "current_weight": 0.5,
  "growth_weight": 2.0,
  "average_weight": 1.0,
  "tie_tolerance": 0.1
}
```

Cada análisis usa observaciones válidas en `[t - window_seconds, t]`, incluidos los extremos
(a 1 Hz, 8 segundos pueden contener 9 muestras). `current_count` es la observación actual;
`previous_count` es la última observación válida anterior dentro de la ventana, y `delta` es
actual menos anterior. `average_count` es el promedio aritmético de las muestras disponibles.
`sample_count` permite saber cuántas observaciones sostienen el cálculo.

La tasa es la pendiente de una regresión lineal simple:

```text
growth_rate = Σ((tᵢ - promedio_t) × (conteoᵢ - promedio_conteo)) / Σ((tᵢ - promedio_t)²)
```

Usar toda la ventana reduce el ruido de diferencias de un solo segundo; se usan los tiempos
reales, no posiciones en una lista. Tasas mayores que `trend_threshold` son `growing`, menores
que su negativo son `decreasing`; el resto es `stable`. No se redondea antes de clasificar.
Con menos de `min_samples`, `growth_rate=null`, `trend=stable` y `status=insufficient_history`:
esa etiqueta neutral no demuestra estabilidad. La consola indica que faltan datos.

La fórmula exacta inicial es:

```text
positive_growth = max(growth_rate, 0) si trend == "growing"; de lo contrario 0
score = 0.5 × current_count + 2.0 × positive_growth + 1.0 × average_count
```

Los coeficientes son iniciales, no calibrados. El peso del promedio supera al instantáneo
para amortiguar variaciones; la banda estable elimina el aporte de crecimientos pequeños.
No hay otro filtro temporal ni permanencia mínima del ganador: aún pueden cambiar prioridades.
El peso de crecimiento convierte veh/s en puntos; los otros pesos convierten vehículos en puntos.
`components` guarda los tres aportes ponderados y `reasons` sus mediciones explicativas.
La prioridad mide ocupación observada, no prueba una cola detenida ni espera acumulada.

Casos especiales:

- Sin zonas: `winner=null`, `reason=no_zones`.
- Todas las zonas actualmente en cero: `winner=null`, `reason=no_demand`, aunque haya promedio histórico.
- Scores superiores separados por hasta `tie_tolerance` puntos: `winner=null`, `reason=tie`.
- Conteos ausentes, negativos o no enteros: se omiten, nunca se imputan como cero. Si falta una
  observación actual, su score es `null` y el resultado es `winner=null`, `reason=missing_data`.
- Historial insuficiente: se calcula demanda y promedio disponibles sin aporte de crecimiento.
- Un hueco histórico conserva sus timestamps; no se inventan muestras intermedias.

El JSONL conserva los tres campos originales y añade `analysis` (por ID de zona) y `priority`.
El resumen mantiene la memoria de `TrafficState`; el análisis completo queda en JSONL.
La consola presenta métricas por zona y los motivos del ganador aproximadamente una vez por
segundo de la fuente. El video conserva polígonos y conteos, sin otro panel.

```powershell
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe app.py --source .\data\videos\trafico_cruce.mp4 --config .\config\intersection.json --output .\output\prueba_analisis
```

Configura primero `waiting_zones`; la configuración inicial vacía muestra `no_zones`.
La ventana no debe superar los 30 segundos de memoria. El promedio no pondera por duración:
es apropiado para muestras aproximadamente a 1 Hz, pero huecos importantes reducen su
representatividad. Ni los pesos ni la tolerancia compensan una mala calibración de polígonos.

Para añadir espera, confianza u otros criterios después, incorpora mediciones explícitas al
análisis y un aporte con su razón en el calculador. No se crean campos ficticios ni interfaces
vacías. La capa de fases y semáforo virtual descrita abajo consume estos scores por zona;
el ganador de zona queda como diagnóstico, no selecciona directamente un verde.

### Fases y semáforo virtual (solo simulación)

Flujo implementado: `TrafficState → Memory → Analysis → PriorityScore → PhaseManager →
TrafficLightController → GREEN / YELLOW / ALL_RED`. No hay conexión a infraestructura real.

`phase_manager.py` valida y agrupa zonas; `traffic_light_controller.py` administra el reloj,
la selección y las transiciones, sin lógica de visión. `simulate_controller.py` recorre estados
ficticios definidos en `config/simulation.json`, sin importar ni ejecutar YOLO.

Configura `traffic_phases` en la configuración del video después de calibrar `waiting_zones`:

```json
"traffic_phases": [
  {"id": "phase_ns", "name": "Norte-Sur", "zones": ["north", "south"]},
  {"id": "phase_ew", "name": "Este-Oeste", "zones": ["east", "west"]}
]
```

Esos IDs son ilustrativos: todos deben existir en `waiting_zones`. Se admite cualquier número
de fases. El código no deduce compatibilidad física ni puntos cardinales; quien configura
determina qué movimientos pueden agruparse. Una zona puede pertenecer a varias fases, pero no
repetirse dentro de una fase. IDs de fase repetidos, fases vacías o zonas desconocidas se rechazan.
Sin fases configuradas, el controlador permanece en TODO-ROJO.

Fórmulas iniciales:

```text
phase_score = suma de scores de las zonas de esa fase
waiting = tiempo desde que terminó su verde (desde inicio de simulación si nunca fue atendida)
bonus = max(0, waiting - starvation_wait_seconds) × starvation_bonus_per_second
effective_score = phase_score + bonus
normalized_demand = clamp(phase_score / reference_score, 0, 1)
green = min_green_seconds + normalized_demand × (max_green_seconds - min_green_seconds)
```

La suma está aislada en `PhaseManager.aggregate`, donde puede sustituirse después. El bonus
afecta a la selección, no prolonga el verde. Una fase sin vehículos actuales recibe el verde
mínimo aunque conserve score histórico. La duración queda fijada al iniciar GREEN.

Parámetros **experimentales de simulación, no tiempos normativos** bajo `simulation_parameters`:

| Parámetro | Video: valor inicial | Ejemplo sintético |
|---|---:|---:|
| `min_green_seconds` | 10 | 5 |
| `max_green_seconds` | 40 | 15 |
| `yellow_seconds` | 3 | 2 |
| `all_red_seconds` | 2 | 1 |
| `reference_score` | 30 | 30 |
| `switch_margin` (puntos) | 1 | 1 |
| `starvation_wait_seconds` | 60 | 25 |
| `starvation_bonus_per_second` (puntos/s) | 1 | 1 |
| `safe_green_seconds` | 15 | 7 |

La configuración inicial de video conserva zonas/fases vacías. El ejemplo de dos fases está
en `config/simulation.json` y no sirve como calibración geométrica del video.

Reglas de operación:

1. Arranca en ALL_RED y cumple su duración antes del primer GREEN.
2. Conserva GREEN hasta completar su plan, incluso si otra fase gana durante ese intervalo.
3. Pasa por YELLOW y ALL_RED, sin omitirlos aunque vuelva a seleccionar la misma fase.
4. Al terminar ALL_RED, reevalúa con la observación más reciente. `next_phase` durante el
   despeje es provisional, nunca un compromiso de activar inmediatamente ese verde.
5. Si alguna fase superó `starvation_wait_seconds`, elige la más atrasada, aun vacía. Esta
   regla tiene precedencia sobre scores y margen: un bonus finito por sí solo no garantiza atención.
6. Si no hay esperas vencidas, considera fases con demanda actual. Dentro de `switch_margin`,
   favorece la fase anterior; en otros empates cercanos usa mayor espera y luego orden del JSON.
7. Con todas las fases vacías rota en orden y usa verde mínimo. Una fase vacía queda diferida
   cuando otras tienen demanda, hasta que se aplica la regla de espera vencida.

El límite de espera es un umbral para la próxima selección, no una garantía de atención
exactamente en ese segundo: no interrumpe un verde ni el despeje. Con más fases atrasadas,
atiende primero la más antigua. `last_served_at` registra el inicio de su último verde;
`waiting_since` es nulo mientras está verde y comienza al salir; `time_since_last_green`
es cero durante el verde y, fuera de él, el tiempo desde el último inicio (nulo si nunca ocurrió).

Confianza inyectada, sin inferir fallos de YOLO:

- `high`: operación adaptativa si hay scores y demanda válidos para todas las fases.
- `low` o datos faltantes: conserva el plan vigente; en la siguiente selección rota por orden,
  con `safe_green_seconds`. No persigue scores ni prolonga indefinidamente la fase actual.
- `error`: enclava `mode=SAFE_MODE`, `safe_mode=true` hasta reiniciar el controlador. Termina
  el plan vigente y usa la misma rotación fija, sin scores adaptativos. Registra pérdida de
  confianza. Un posterior `high` no lo desactiva automáticamente.

SAFE_MODE es un modo de operación, no un cuarto color: sigue recorriendo GREEN → YELLOW →
ALL_RED. `safe_green_seconds` debe estar entre mínimo y máximo. Amarillo y TODO-ROJO usan sus
parámetros de simulación en todos los modos. En ausencia de fases permanece TODO-ROJO.

Observación y persistencia:

- El análisis conserva su muestreo a aproximadamente 1 Hz; el controlador avanza por frame.
- El JSONL mantiene `timestamp`, `vehicles_by_zone`, `total_vehicles`, `analysis` y `priority`.
  Añade `phase_priorities` con componentes/bonus, fase/estado actuales, relojes, verde planificado,
  restante, siguiente fase, decisión, razones, confianza, modo y seguimiento de espera.
- Los estados de tráfico siguen en los campos originales; `analysis` y `priority` representan
  análisis y prioridades de zona. No se duplican bajo otros nombres.
- Se registra cada muestra y también cada transición entre muestras. `analysis_timestamp`
  identifica la última observación analizada si el evento ocurrió entre dos segundos.
- El resumen guarda fases, parámetros y confianza inyectada. El video añade una sola línea
  inferior con la leyenda SIMULACION, fase, color, restante y modo.

Ejecutar escenarios ficticios (superioridad NS/EW, cambio de demanda, ceros, low y error):

```powershell
.\.venv\Scripts\python.exe simulate_controller.py --config .\config\simulation.json --output .\output\simulation.jsonl
.\.venv\Scripts\python.exe -m unittest -v
```

El simulador aplica los conteos del último evento hasta el siguiente. Edita los eventos y sus
timestamps en el JSON para probar otras secuencias. Sus datos son artificiales, no detecciones.

Con video, después de configurar zonas y fases:

```powershell
.\.venv\Scripts\python.exe app.py --source .\data\videos\trafico_cruce.mp4 --config .\config\intersection.json --output .\output\prueba_semaforo --simulation-confidence high
```

Usa `--simulation-confidence low` o `error` para inyectar esos modos durante toda la ejecución.
La simulación independiente permite cambiar confianza durante el recorrido.

Limitaciones: las transiciones ocurren en la primera llamada que alcanza el plazo; el muestreo
puede exceder el verde planificado por hasta un intervalo entre llamadas (en video, un frame;
en el simulador, un segundo). Si el reloj salta, se inicia el siguiente estado en el momento
observado, sin inventar transiciones pasadas ni omitir despejes. Por eso no es un temporizador
para infraestructura real. La prioridad depende de ocupación y no mide esperas individuales.

Siguiente etapa propuesta: calibrar zonas y compatibilidad de movimientos, evaluar espera y
oscilación en clips más largos, y acordar criterios de recuperación de confianza. No se añaden
aprendizaje, peatones avanzados, emergencias ni control físico.

- El video muestra líneas, sentidos, cruces, objetos visibles, máximo simultáneo y FPS.
- El CSV registra esas métricas por fotograma y el tiempo de procesamiento.
- El JSON separa datos del video, rendimiento total, rendimiento tras 10 fotogramas de calentamiento, máximos, cruces e IDs observados.

Los IDs observados son únicamente un dato diagnóstico: ByteTrack puede reasignarlos después de una oclusión, por lo que no representan objetos únicos ni flujo real.

## Comprobaciones rápidas

```powershell
python -m py_compile app.py
python -m unittest test_app.py
python -m json.tool config\intersection.json
python app.py --help
```

## Documentación

- [Decisión tecnológica](docs/decision_tecnologica.md)
- [Contrato de datos](docs/contrato_datos.md)
- [Protocolo de evaluación](docs/protocolo_evaluacion.md)
- [Bitácora](docs/bitacora.md)
- [Guía de colaboración](CONTRIBUTING.md)

La procedencia y características de los clips se registran en [`data/catalogo_clips.csv`](data/catalogo_clips.csv).
