# Contrato inicial de datos

## Entrada del detector

| Campo | Tipo | Descripción |
|---|---|---|
| `source` | ruta o entero | Video grabado o índice de cámara |
| `model` | texto | Archivo de pesos YOLO |
| `confidence_threshold` | decimal | Confianza mínima aceptada, de 0 a 1 |
| `classes` | lista | Clases COCO que se analizarán |

La configuración física preliminar de la intersección se guarda en `config/intersection.json`.

## Salidas

1. Video MP4 anotado con cajas, etiquetas e identificadores de seguimiento.
2. CSV con detecciones actuales y objetos únicos acumulados por fotograma.
3. JSON de resumen con fuente, modelo, dispositivo, fotogramas, FPS y conteos.

Ejemplo abreviado del resumen:

```json
{
  "source": "data/videos/trafico.mp4",
  "model": "yolo11n.pt",
  "frames_processed": 900,
  "average_processing_fps": 31.4,
  "unique_objects_by_class": {
    "persona": 8,
    "automovil": 24
  }
}
```

## Interpretación

`actual_automovil` indica cuántos automóviles aparecen en un fotograma. `unicos_automovil` representa IDs distintos observados hasta ese momento. No debe interpretarse todavía como flujo vehicular validado, porque las oclusiones pueden reasignar IDs.
