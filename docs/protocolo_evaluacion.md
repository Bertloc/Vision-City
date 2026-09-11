# Protocolo preliminar de evaluación

## Propósito

Evaluar de forma reproducible la prueba de concepto sin afirmar que ya se alcanzaron las metas finales del proyecto.

## Conjunto inicial

Preparar de dos a tres clips de 20–60 segundos con diferentes condiciones: tránsito moderado, presencia de peatones y alguna oclusión. Registrar procedencia, licencia, duración, resolución, FPS, iluminación y cámara.

## Procedimiento

1. Conservar una copia sin modificar de cada clip.
2. Ejecutar siempre el mismo modelo y umbral de confianza.
3. Guardar video procesado, CSV y resumen JSON.
4. Seleccionar fotogramas distribuidos a lo largo del clip y contar manualmente los objetos visibles.
5. Comparar la anotación manual con la salida automática.
6. Registrar falsos positivos, falsos negativos, cambios de ID y condiciones difíciles.

## Métricas iniciales

| Métrica | Cálculo o evidencia |
|---|---|
| Precisión | VP / (VP + FP) |
| Exhaustividad | VP / (VP + FN) |
| Rendimiento | FPS promedio de procesamiento |
| Latencia aproximada | 1 / FPS promedio |
| Estabilidad del conteo | Cambios de ID observados manualmente |

VP significa verdadero positivo, FP falso positivo y FN falso negativo.

## Criterio para el avance

La demostración se considera operable si abre un clip, detecta las clases seleccionadas, produce los tres archivos de salida y termina sin errores. Las metas finales de precisión y reducción de espera no se validan en esta etapa.
