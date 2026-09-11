# Bitácora del proyecto

## 11 de septiembre de 2026

### Primera prueba operativa

- Se ejecutó `trafico_cruce.mp4`: 7.2 segundos, 1280 × 720, 30 FPS y 216 fotogramas.
- La prueba terminó y produjo video, CSV y JSON en una NVIDIA GeForce GTX 1660 SUPER.
- El contador anterior informó 80 personas, 38 automóviles, 1 autobús y 6 camiones mediante IDs acumulados.
- La revisión visual mostró que ByteTrack pierde objetos y asigna IDs nuevos al recuperarlos. Por ello esos valores presentan sobreconteo y no representan objetos únicos ni flujo real.

### Corrección implementada

- Se sustituyó el conteo acumulado de IDs por cruces de líneas virtuales configurables.
- Se añadieron una línea horizontal para vehículos y una vertical para peatones, ambas con coordenadas normalizadas, sentidos, clases e histéresis.
- Se separaron objetos visibles, máximos simultáneos, cruces e IDs observados como diagnóstico.
- Se añadieron tiempos por fotograma, rendimiento total con inicialización y rendimiento estable sin los primeros 10 fotogramas.
- Se actualizaron el video anotado, el CSV, el JSON y la documentación del contrato y evaluación.

### Verificación preliminar

La ejecución corregida procesó los 216 fotogramas y generó los tres archivos esperados. Se inspeccionaron los fotogramas 0, 72, 144 y 215 del MP4; las líneas, nombres, sentidos y métricas fueron visibles.

- Máximos simultáneos: 10 personas, 9 automóviles, 1 autobús y 1 camión; 0 bicicletas y motocicletas.
- Línea de vehículos: 2 automóviles hacia abajo y 2 hacia arriba.
- Línea de peatones: 1 persona de derecha a izquierda y 0 en sentido contrario.
- Rendimiento total con inicialización: 14.51 FPS.
- Rendimiento estable después de 10 fotogramas: 24.18 FPS.
- Tiempo por fotograma: mediana de 40.96 ms y percentil 95 de 50.09 ms.
- IDs observados: 125 en total, conservados exclusivamente como diagnóstico.

Los cinco cruces parecen plausibles en esta revisión visual parcial, pero las posiciones aún requieren calibración y comparación evento por evento contra anotación manual.

### Estado honesto

La corrección no se declara validada. No se reportan precisión, reducción del tiempo de espera ni cantidad real de vehículos. Los resultados siguen siendo preliminares hasta completar anotación manual.

### Siguientes pasos

1. Anotar manualmente cruces por línea, clase y dirección.
2. Calibrar cada segmento para el encuadre real de la cámara.
3. Comparar los eventos y documentar falsos cruces y cruces omitidos.
4. Repetir con clips más largos y condiciones variadas.
