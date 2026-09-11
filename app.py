"""Prueba de concepto de detección y seguimiento para Visión City."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

COCO_CLASSES = {
    0: "persona",
    1: "bicicleta",
    2: "automovil",
    3: "motocicleta",
    5: "autobus",
    7: "camion",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detecta y rastrea vehículos y peatones en un video."
    )
    parser.add_argument("--source", required=True, help="Ruta del video o índice de cámara.")
    parser.add_argument("--model", default="yolo11n.pt", help="Pesos del modelo YOLO.")
    parser.add_argument("--conf", type=float, default=0.35, help="Confianza mínima (0-1).")
    parser.add_argument("--show", action="store_true", help="Muestra la ventana durante el proceso.")
    parser.add_argument("--output", default="output", help="Directorio de resultados.")
    return parser.parse_args()


def open_source(source: str) -> cv2.VideoCapture:
    capture_source: int | str = int(source) if source.isdigit() else source
    capture = cv2.VideoCapture(capture_source)
    if not capture.isOpened():
        raise FileNotFoundError(f"No se pudo abrir la fuente: {source}")
    return capture


def prepare_outputs(output_root: Path, source: str) -> tuple[Path, Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source_name = Path(source).stem if not source.isdigit() else f"camara_{source}"
    video_dir = output_root / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return (
        video_dir / f"{source_name}_{stamp}_detectado.mp4",
        output_root / f"{source_name}_{stamp}_fotogramas.csv",
        output_root / f"{source_name}_{stamp}_resumen.json",
    )


def main() -> None:
    args = parse_args()
    if not 0 < args.conf <= 1:
        raise ValueError("--conf debe ser mayor que 0 y menor o igual que 1.")

    device = 0 if torch.cuda.is_available() else "cpu"
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"Dispositivo: {device_name}")
    print(f"Cargando modelo: {args.model}")

    model = YOLO(args.model)
    capture = open_source(args.source)
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    source_fps = source_fps if source_fps > 0 else 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))

    video_path, csv_path, summary_path = prepare_outputs(Path(args.output), args.source)
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), source_fps, (width, height)
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("No se pudo crear el video de salida.")

    unique_ids: dict[str, set[int]] = defaultdict(set)
    frame_index = 0
    total_processing_time = 0.0
    fieldnames = ["fotograma", "segundo", "fps_procesamiento"]
    fieldnames += [f"actual_{name}" for name in COCO_CLASSES.values()]
    fieldnames += [f"unicos_{name}" for name in COCO_CLASSES.values()]

    with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        csv_writer.writeheader()

        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                started = time.perf_counter()
                result = model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    classes=list(COCO_CLASSES),
                    conf=args.conf,
                    device=device,
                    verbose=False,
                )[0]
                elapsed = time.perf_counter() - started
                total_processing_time += elapsed
                processing_fps = 1.0 / elapsed if elapsed else 0.0

                current_counts = {name: 0 for name in COCO_CLASSES.values()}
                boxes = result.boxes
                if boxes is not None and boxes.cls is not None:
                    class_ids = boxes.cls.int().cpu().tolist()
                    track_ids = (
                        boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(class_ids)
                    )
                    for class_id, track_id in zip(class_ids, track_ids):
                        name = COCO_CLASSES[class_id]
                        current_counts[name] += 1
                        if track_id is not None:
                            unique_ids[name].add(track_id)

                annotated = result.plot()
                unique_total = sum(len(ids) for ids in unique_ids.values())
                cv2.putText(
                    annotated,
                    f"Objetos unicos: {unique_total} | FPS proceso: {processing_fps:.1f}",
                    (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 255, 255),
                    2,
                )
                writer.write(annotated)

                row: dict[str, int | float] = {
                    "fotograma": frame_index,
                    "segundo": round(frame_index / source_fps, 3),
                    "fps_procesamiento": round(processing_fps, 2),
                }
                row.update({f"actual_{name}": count for name, count in current_counts.items()})
                row.update({f"unicos_{name}": len(unique_ids[name]) for name in COCO_CLASSES.values()})
                csv_writer.writerow(row)

                if args.show:
                    cv2.imshow("Vision City - presiona Q para salir", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                frame_index += 1
        finally:
            capture.release()
            writer.release()
            cv2.destroyAllWindows()

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": args.source,
        "model": args.model,
        "confidence_threshold": args.conf,
        "device": device_name,
        "frames_processed": frame_index,
        "source_fps": round(source_fps, 2),
        "video_duration_seconds": round(frame_index / source_fps, 2),
        "average_processing_fps": round(
            frame_index / total_processing_time if total_processing_time else 0.0, 2
        ),
        "unique_objects_by_class": {
            name: len(unique_ids[name]) for name in COCO_CLASSES.values()
        },
        "warning": "Resultados preliminares; los IDs del rastreador pueden cambiar por oclusiones.",
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Proceso terminado.")
    print(f"Video: {video_path}")
    print(f"CSV: {csv_path}")
    print(f"Resumen: {summary_path}")


if __name__ == "__main__":
    main()
