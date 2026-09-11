# Protocolo preliminar de evaluación

## Propósito

Evaluar de forma reproducible la prueba de concepto sin afirmar precisión, flujo real ni reducción de tiempos de espera antes de contar con anotación manual.

## Conjunto inicial

Preparar de dos a tres clips de 20–60 segundos con tránsito, peatones y oclusiones. Registrar procedencia, licencia, duración, resolución, FPS, iluminación y cámara en `data/catalogo_clips.csv`. El clip corto `trafico_cruce.mp4` sirve para una comprobación operativa, no como conjunto de validación.

## Calibración por cámara

1. Abrir un fotograma representativo sin alterar el video fuente.
2. Ajustar `start` y `end` de cada línea con coordenadas normalizadas.
3. Orientar la línea y asignar nombres inequívocos a `positive` y `negative`.
4. Limitar `classes` al tránsito que realmente corresponde a la línea.
5. Ajustar `hysteresis` solo si se observa vibración cerca de la línea.
6. Documentar la configuración utilizada; no reutilizar coordenadas sin revisar el encuadre.

## Procedimiento

1. Conservar una copia sin modificar de cada clip.
2. Ejecutar siempre el mismo modelo, umbral y configuración de líneas.
3. Procesar sin `--show` para evitar bloqueos y guardar MP4, CSV y JSON.
4. Verificar que el número de fotogramas, duración, resolución y FPS coincidan con la fuente.
5. Revisar fotogramas al inicio, durante y al final; confirmar líneas, sentidos y legibilidad.
6. Anotar manualmente cada cruce por línea, clase y dirección.
7. Comparar eventos manuales y automáticos, registrando falsos cruces, cruces omitidos, oclusiones y cambios de ID.
8. Repetir después de cualquier ajuste de línea, histéresis, modelo o confianza.

## Métricas

| Métrica | Cálculo o evidencia |
|---|---|
| Objetos visibles | Detecciones de la clase en cada fotograma |
| Máximo simultáneo | Mayor conteo visible por clase durante el clip |
| Cruces | Eventos acumulados por línea, clase y dirección |
| IDs observados | Diagnóstico de estabilidad del rastreador, no flujo real |
| FPS total | Fotogramas / (inicialización + tiempos de detección y rastreo) |
| FPS estable | Fotogramas posteriores al décimo / sus tiempos de procesamiento |
| Tiempo mediano y P95 | Distribución medida de tiempos por fotograma |
| Precisión de cruces | Solo después de emparejar eventos automáticos y manuales |

## Criterio de avance

La demostración es operable si termina sin errores y produce MP4, CSV y JSON coherentes. El conteo por línea se considera validado únicamente cuando se compara contra anotación manual suficiente. Hasta entonces, todos los resultados y posiciones de línea se reportan como preliminares.
