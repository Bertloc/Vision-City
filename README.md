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
