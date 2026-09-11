# Contrato de datos

## Entrada

| Campo CLI | Tipo | Descripción |
|---|---|---|
| `--source` | ruta o entero | Video grabado o índice de cámara; obligatorio |
| `--config` | ruta | JSON de intersección; predeterminado `config/intersection.json` |
| `--model` | texto | Pesos YOLO; si se omite usa `detection.model` |
| `--conf` | decimal | Confianza de 0 a 1; si se omite usa `detection.confidence_threshold` |
| `--show` | bandera | Activa la ventana de vista previa |
| `--output` | ruta | Directorio de resultados; predeterminado `output` |

## Configuración de líneas

`counting_lines` es una lista de objetos con estos campos:

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | texto | Identificador único usado en CSV y JSON |
| `name` | texto | Nombre mostrado en el video |
| `start`, `end` | `[x, y]` | Extremos normalizados entre 0 y 1 |
| `classes` | lista | Clases que pueden cruzar esa línea |
| `directions.positive` | texto | Nombre del cruce del lado negativo al positivo |
| `directions.negative` | texto | Nombre del cruce del lado positivo al negativo |
| `hysteresis` | decimal | Distancia normalizada que forma la banda neutral |

El lado se calcula con el producto cruzado respecto de la línea orientada de `start` a `end`. Las coordenadas, el segmento y la histéresis son parámetros preliminares que requieren calibración para cada cámara.

## Video MP4

Contiene cajas y etiquetas de YOLO, líneas virtuales, nombres y sentidos, conteos acumulados por línea, objetos visibles, máximos simultáneos y FPS del fotograma. Un panel oscuro separa las métricas de las etiquetas.

## CSV por fotograma

Columnas fijas:

- `fotograma`, `segundo`, `fps_procesamiento`, `tiempo_procesamiento_ms`.
- `visibles_<clase>` y `max_simultaneo_<clase>` para las seis clases.
- `cruces_<id_linea>_positive` y `cruces_<id_linea>_negative`, acumulados hasta ese fotograma.

## Resumen JSON

```json
{
  "video": {
    "source": ".\\data\\videos\\trafico_cruce.mp4",
    "width": 1280,
    "height": 720,
    "source_fps": 30.0,
    "duration_seconds": 7.2
  },
  "model": "yolo11n.pt",
  "confidence_threshold": 0.35,
  "device": "NVIDIA GeForce GTX 1660 SUPER",
  "frames_processed": 216,
  "performance": {
    "average_fps_total": 0.0,
    "average_fps_after_warmup": 0.0,
    "median_frame_time_ms": 0.0,
    "p95_frame_time_ms": 0.0
  },
  "maximum_simultaneous_by_class": {},
  "crossings": {},
  "tracking_ids_observed": {
    "note": "Dato diagnóstico; no representa objetos únicos ni flujo real."
  }
}
```

`average_fps_total` incluye la inicialización. `average_fps_after_warmup` excluye los primeros 10 fotogramas. Los tiempos por fotograma miden detección y rastreo; `wall_clock_elapsed_seconds` conserva además el tiempo transcurrido de la ejecución completa.

`crossings` separa cada línea, clase y dirección e incluye totales por sentido. `tracking_ids_observed` nunca debe presentarse como cantidad real de objetos o flujo vehicular.
