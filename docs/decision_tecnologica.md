# Decisión tecnológica inicial

**Fecha:** 11 de septiembre de 2026  
**Estado:** aceptada para la prueba de concepto

## Decisión

Se utilizará Python como lenguaje, OpenCV para lectura y escritura de video, y un modelo YOLO preentrenado mediante Ultralytics para detectar y rastrear peatones y vehículos.

## Razones

- Permite producir una prueba funcional en el tiempo disponible.
- El modelo preentrenado ya contempla las clases necesarias para esta etapa.
- OpenCV facilita trabajar primero con videos grabados y después con una cámara.
- La solución puede ejecutarse con CPU o aprovechar la GTX 1660 Super si PyTorch reconoce CUDA.

## Modelo inicial

Se propone `yolo11n.pt` por su bajo costo computacional. Esta elección es preliminar: más adelante se comparará con otro tamaño de modelo utilizando el mismo conjunto de prueba.

## Cámara y hardware por etapas

| Etapa | Fuente | Equipo de procesamiento |
|---|---|---|
| Prueba de concepto | Video grabado público | PC con Windows y GTX 1660 Super |
| Prueba controlada | Webcam USB o teléfono como cámara IP | La misma PC |
| Piloto futuro | Cámara IP 1080p, 20–30 FPS, posición elevada | PC o equipo de borde por evaluar |

No se recomienda comprar cámara o equipo de borde hasta medir resolución, iluminación, latencia y campo de visión requeridos.

## Riesgos y límites

- El modelo no fue entrenado específicamente para la intersección objetivo.
- Oclusiones, lluvia, noche y ángulos deficientes pueden reducir el desempeño.
- Un ID de seguimiento puede cambiar cuando un objeto desaparece y reaparece.
- La licencia y condiciones de distribución de cada dependencia deberán revisarse antes de una implementación comercial.
