# Visión City

Prototipo académico de visión artificial para detectar y contabilizar vehículos y peatones en video. Forma parte del Sprint I del proyecto **Visión City**.

> Estado actual: preparación técnica y prueba de concepto. El sistema todavía no controla semáforos ni reporta métricas finales de precisión.

## Objetivo de esta etapa

- Definir la tecnología y los contratos básicos entre módulos.
- Preparar videos y un protocolo inicial de evaluación.
- Ejecutar una prueba de concepto con Python, OpenCV y YOLO.
- Generar evidencia reproducible: video procesado, conteos, CSV y métricas de rendimiento.

## Clases consideradas

- Persona
- Bicicleta
- Automóvil
- Motocicleta
- Autobús
- Camión

## Requisitos

- Windows 10/11
- Python 3.10–3.12 recomendado
- Git
- GPU NVIDIA opcional; la aplicación también puede ejecutarse con CPU

## Inicio rápido

```powershell
git clone https://github.com/Bertloc/Vision-City.git
cd Vision-City
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Coloca un video en `data/videos/` y ejecuta:

```powershell
python app.py --source data/videos/trafico.mp4
```

Los resultados se guardan en `output/`.

## Estructura

```text
Vision-City/
├── app.py
├── config/intersection.json
├── data/
│   ├── catalogo_clips.csv
│   └── videos/
├── docs/
├── output/
├── .gitignore
├── CONTRIBUTING.md
└── requirements.txt
```

## Documentación

- [Decisión tecnológica](docs/decision_tecnologica.md)
- [Contrato de datos](docs/contrato_datos.md)
- [Protocolo de evaluación](docs/protocolo_evaluacion.md)
- [Bitácora](docs/bitacora.md)
- [Guía de colaboración](CONTRIBUTING.md)

Los videos no se suben al repositorio. Su origen y características se registran en
[`data/catalogo_clips.csv`](data/catalogo_clips.csv).

## Alcance excluido por ahora

No se incluye entrenamiento desde cero, reconocimiento facial o de placas, control físico de semáforos, dashboard completo ni medición de reducción de tiempos de espera.

## Equipo

Proyecto académico colaborativo. Los integrantes y responsabilidades se registrarán en la bitácora.
