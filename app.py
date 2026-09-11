"""Detección, seguimiento y conteo por líneas virtuales para Visión City."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

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
WARMUP_FRAMES = 10
Point = tuple[float, float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detecta, rastrea y cuenta cruces de vehículos y peatones."
    )
    parser.add_argument("--source", required=True, help="Ruta del video o índice de cámara.")
    parser.add_argument(
        "--config",
        default="config/intersection.json",
        help="Configuración de la intersección y sus líneas virtuales.",
    )
    parser.add_argument("--model", help="Pesos YOLO; reemplaza el valor de la configuración.")
    parser.add_argument(
        "--conf",
        type=float,
        help="Confianza mínima (0-1); reemplaza el valor de la configuración.",
    )
    parser.add_argument("--show", action="store_true", help="Muestra la ventana durante el proceso.")
    parser.add_argument("--output", default="output", help="Directorio de resultados.")
    return parser.parse_args()


def _normalized_point(value: Any, field: str) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field} debe ser una lista [x, y].")
    try:
        point = (float(value[0]), float(value[1]))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} debe contener números.") from error
    if not all(0.0 <= coordinate <= 1.0 for coordinate in point):
        raise ValueError(f"{field} debe usar coordenadas entre 0 y 1.")
    return point


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    lines = config.get("counting_lines")
    if not isinstance(lines, list) or not lines:
        raise ValueError("La configuración debe incluir al menos una counting_line.")

    known_classes = set(COCO_CLASSES.values())
    seen_ids: set[str] = set()
    for index, line in enumerate(lines):
        prefix = f"counting_lines[{index}]"
        line_id = line.get("id")
        if not isinstance(line_id, str) or not line_id.strip() or line_id in seen_ids:
            raise ValueError(f"{prefix}.id debe ser un identificador único no vacío.")
        seen_ids.add(line_id)
        if not isinstance(line.get("name"), str) or not line["name"].strip():
            raise ValueError(f"{prefix}.name debe ser texto no vacío.")
        line["start"] = _normalized_point(line.get("start"), f"{prefix}.start")
        line["end"] = _normalized_point(line.get("end"), f"{prefix}.end")
        if line["start"] == line["end"]:
            raise ValueError(f"{prefix} debe tener puntos inicial y final diferentes.")
        classes = line.get("classes")
        if not isinstance(classes, list) or not classes or not set(classes) <= known_classes:
            raise ValueError(f"{prefix}.classes contiene clases desconocidas o está vacío.")
        directions = line.get("directions")
        if not isinstance(directions, dict) or not all(
            isinstance(directions.get(key), str) and directions[key].strip()
            for key in ("positive", "negative")
        ):
            raise ValueError(f"{prefix}.directions debe definir positive y negative.")
        hysteresis = line.get("hysteresis", 0.01)
        if not isinstance(hysteresis, (int, float)) or not 0 < hysteresis < 0.25:
            raise ValueError(f"{prefix}.hysteresis debe estar entre 0 y 0.25.")
        line["hysteresis"] = float(hysteresis)
    return config


def signed_distance(point: Point, start: Point, end: Point) -> float:
    """Distancia perpendicular con signo respecto de una línea orientada."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    return (dx * (point[1] - start[1]) - dy * (point[0] - start[0])) / math.hypot(
        dx, dy
    )


def stable_side(point: Point, start: Point, end: Point, hysteresis: float) -> int:
    """Devuelve -1, 0 o 1; cero representa la banda de histéresis."""
    distance = signed_distance(point, start, end)
    return 1 if distance > hysteresis else -1 if distance < -hysteresis else 0


def crossing_within_segment(previous: Point, current: Point, start: Point, end: Point) -> bool:
    """Comprueba que la trayectoria cruce la parte finita de la línea."""
    previous_distance = signed_distance(previous, start, end)
    current_distance = signed_distance(current, start, end)
    denominator = previous_distance - current_distance
    if denominator == 0:
        return False
    motion_fraction = previous_distance / denominator
    if not 0.0 <= motion_fraction <= 1.0:
        return False
    crossing = (
        previous[0] + motion_fraction * (current[0] - previous[0]),
        previous[1] + motion_fraction * (current[1] - previous[1]),
    )
    line_x, line_y = end[0] - start[0], end[1] - start[1]
    projection = (
        (crossing[0] - start[0]) * line_x + (crossing[1] - start[1]) * line_y
    ) / (line_x * line_x + line_y * line_y)
    return 0.0 <= projection <= 1.0


def percentile(values: list[float], percentage: float) -> float:
    """Percentil con interpolación lineal, sin dependencias adicionales."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


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


def to_pixel(point: Point, width: int, height: int) -> tuple[int, int]:
    return round(point[0] * (width - 1)), round(point[1] * (height - 1))


def cv_text(text: str) -> str:
    """Convierte texto a caracteres que la fuente integrada de OpenCV puede dibujar."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def draw_label(frame: Any, text: str, position: tuple[int, int], color: tuple[int, int, int]) -> None:
    text = cv_text(text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.48
    thickness = 1
    (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)
    x = max(0, min(position[0], frame.shape[1] - text_width - 6))
    y = max(text_height + 4, min(position[1], frame.shape[0] - baseline - 4))
    cv2.rectangle(
        frame,
        (x - 3, y - text_height - 3),
        (x + text_width + 3, y + baseline + 3),
        (0, 0, 0),
        -1,
    )
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def draw_counting_lines(frame: Any, lines: list[dict[str, Any]]) -> None:
    height, width = frame.shape[:2]
    for line in lines:
        start = to_pixel(line["start"], width, height)
        end = to_pixel(line["end"], width, height)
        cv2.line(frame, start, end, (0, 215, 255), 3, cv2.LINE_AA)
        midpoint = ((start[0] + end[0]) // 2, (start[1] + end[1]) // 2)
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        normal = (-dy / length, dx / length)
        positive = (round(midpoint[0] + normal[0] * 42), round(midpoint[1] + normal[1] * 42))
        negative = (round(midpoint[0] - normal[0] * 42), round(midpoint[1] - normal[1] * 42))
        cv2.arrowedLine(frame, midpoint, positive, (0, 255, 0), 2, tipLength=0.3)
        cv2.arrowedLine(frame, midpoint, negative, (0, 128, 255), 2, tipLength=0.3)
        draw_label(frame, line["name"], (start[0], start[1] - 8), (0, 215, 255))
        draw_label(frame, f"+ {line['directions']['positive']}", positive, (0, 255, 0))
        draw_label(frame, f"- {line['directions']['negative']}", negative, (0, 128, 255))


def draw_metrics_panel(
    frame: Any,
    current_counts: dict[str, int],
    maximum_counts: dict[str, int],
    crossing_counts: dict[str, dict[str, dict[str, int]]],
    lines: list[dict[str, Any]],
    processing_fps: float,
) -> None:
    rows = [
        "Visibles: "
        + " | ".join(f"{name} {current_counts[name]}" for name in COCO_CLASSES.values()),
        "Máximo simultáneo: "
        + " | ".join(f"{name} {maximum_counts[name]}" for name in COCO_CLASSES.values()),
        f"FPS de procesamiento: {processing_fps:.1f}",
    ]
    for line in lines:
        totals = {
            direction: sum(
                class_counts[direction]
                for class_counts in crossing_counts[line["id"]].values()
            )
            for direction in ("positive", "negative")
        }
        rows.append(
            f"{line['name']}: {line['directions']['positive']} {totals['positive']} | "
            f"{line['directions']['negative']} {totals['negative']}"
        )
    rows = [cv_text(row) for row in rows]

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.5
    row_height = 22
    panel_width = min(
        frame.shape[1] - 20,
        max(cv2.getTextSize(row, font, scale, 1)[0][0] for row in rows) + 20,
    )
    overlay = frame.copy()
    cv2.rectangle(
        overlay,
        (8, 8),
        (8 + panel_width, 18 + row_height * len(rows)),
        (0, 0, 0),
        -1,
    )
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)
    for index, row in enumerate(rows):
        cv2.putText(
            frame,
            row,
            (15, 27 + index * row_height),
            font,
            scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


def build_crossing_summary(
    lines: list[dict[str, Any]], crossing_counts: dict[str, dict[str, dict[str, int]]]
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for line in lines:
        line_counts = crossing_counts[line["id"]]
        summary[line["id"]] = {
            "name": line["name"],
            "directions": line["directions"],
            "by_class": line_counts,
            "totals": {
                direction: sum(counts[direction] for counts in line_counts.values())
                for direction in ("positive", "negative")
            },
        }
    return summary


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))
    detection_config = config.get("detection", {})
    model_name = args.model or detection_config.get("model", "yolo11n.pt")
    confidence = (
        args.conf
        if args.conf is not None
        else detection_config.get("confidence_threshold", 0.35)
    )
    if not isinstance(confidence, (int, float)) or not 0 < confidence <= 1:
        raise ValueError("La confianza debe ser mayor que 0 y menor o igual que 1.")

    device = 0 if torch.cuda.is_available() else "cpu"
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    print(f"Dispositivo: {device_name}")
    print(f"Cargando modelo: {model_name}")

    total_started = time.perf_counter()
    initialization_started = total_started
    model = YOLO(model_name)
    capture = open_source(args.source)
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    source_fps = source_fps if source_fps > 0 else 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    initialization_seconds = time.perf_counter() - initialization_started

    video_path, csv_path, summary_path = prepare_outputs(Path(args.output), args.source)
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), source_fps, (width, height)
    )
    if not writer.isOpened():
        capture.release()
        raise RuntimeError("No se pudo crear el video de salida.")

    lines = config["counting_lines"]
    observed_ids: dict[str, set[int]] = defaultdict(set)
    track_history: dict[int, deque[Point]] = defaultdict(lambda: deque(maxlen=30))
    line_states: dict[tuple[str, int], tuple[int, Point]] = {}
    counted_tracks: set[tuple[str, int]] = set()
    crossing_counts = {
        line["id"]: {
            class_name: {"positive": 0, "negative": 0} for class_name in line["classes"]
        }
        for line in lines
    }
    maximum_counts = {name: 0 for name in COCO_CLASSES.values()}
    frame_times: list[float] = []
    frame_index = 0
    fieldnames = [
        "fotograma",
        "segundo",
        "fps_procesamiento",
        "tiempo_procesamiento_ms",
    ]
    fieldnames += [f"visibles_{name}" for name in COCO_CLASSES.values()]
    fieldnames += [f"max_simultaneo_{name}" for name in COCO_CLASSES.values()]
    fieldnames += [
        f"cruces_{line['id']}_{direction}"
        for line in lines
        for direction in ("positive", "negative")
    ]

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
                    conf=float(confidence),
                    device=device,
                    verbose=False,
                )[0]
                elapsed = time.perf_counter() - started
                frame_times.append(elapsed)
                processing_fps = 1.0 / elapsed if elapsed else 0.0

                current_counts = {name: 0 for name in COCO_CLASSES.values()}
                boxes = result.boxes
                if boxes is not None and boxes.cls is not None:
                    class_ids = boxes.cls.int().cpu().tolist()
                    track_ids = (
                        boxes.id.int().cpu().tolist()
                        if boxes.id is not None
                        else [None] * len(class_ids)
                    )
                    coordinates = boxes.xyxy.cpu().tolist()
                    for class_id, track_id, (x1, y1, x2, y2) in zip(
                        class_ids, track_ids, coordinates
                    ):
                        class_name = COCO_CLASSES.get(class_id)
                        if class_name is None:
                            continue
                        current_counts[class_name] += 1
                        if track_id is None:
                            continue
                        observed_ids[class_name].add(track_id)
                        center = ((x1 + x2) / (2 * width), (y1 + y2) / (2 * height))
                        track_history[track_id].append(center)

                        for line in lines:
                            if class_name not in line["classes"]:
                                continue
                            side = stable_side(
                                center, line["start"], line["end"], line["hysteresis"]
                            )
                            if side == 0:
                                continue
                            state_key = (line["id"], track_id)
                            previous_state = line_states.get(state_key)
                            if previous_state is not None and side != previous_state[0]:
                                if state_key not in counted_tracks and crossing_within_segment(
                                    previous_state[1], center, line["start"], line["end"]
                                ):
                                    direction = "positive" if side > 0 else "negative"
                                    crossing_counts[line["id"]][class_name][direction] += 1
                                    counted_tracks.add(state_key)
                            line_states[state_key] = (side, center)

                maximum_counts = {
                    name: max(maximum_counts[name], current_counts[name])
                    for name in COCO_CLASSES.values()
                }
                annotated = result.plot()
                draw_counting_lines(annotated, lines)
                draw_metrics_panel(
                    annotated,
                    current_counts,
                    maximum_counts,
                    crossing_counts,
                    lines,
                    processing_fps,
                )
                writer.write(annotated)

                row: dict[str, int | float] = {
                    "fotograma": frame_index,
                    "segundo": round(frame_index / source_fps, 3),
                    "fps_procesamiento": round(processing_fps, 2),
                    "tiempo_procesamiento_ms": round(elapsed * 1000, 2),
                }
                row.update(
                    {f"visibles_{name}": count for name, count in current_counts.items()}
                )
                row.update(
                    {f"max_simultaneo_{name}": count for name, count in maximum_counts.items()}
                )
                for line in lines:
                    for direction in ("positive", "negative"):
                        row[f"cruces_{line['id']}_{direction}"] = sum(
                            counts[direction]
                            for counts in crossing_counts[line["id"]].values()
                        )
                csv_writer.writerow(row)
                frame_index += 1

                if args.show:
                    cv2.imshow("Vision City - presiona Q para salir", annotated)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
        finally:
            capture.release()
            writer.release()
            cv2.destroyAllWindows()

    wall_clock_elapsed = time.perf_counter() - total_started
    total_processing_seconds = initialization_seconds + sum(frame_times)
    stable_times = frame_times[WARMUP_FRAMES:]
    diagnostic_by_class = {
        name: len(observed_ids[name]) for name in COCO_CLASSES.values()
    }
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "video": {
            "source": args.source,
            "width": width,
            "height": height,
            "source_fps": round(source_fps, 2),
            "duration_seconds": round(frame_index / source_fps, 2),
        },
        "model": model_name,
        "confidence_threshold": float(confidence),
        "device": device_name,
        "frames_processed": frame_index,
        "performance": {
            "initialization_seconds": round(initialization_seconds, 3),
            "total_processing_seconds": round(total_processing_seconds, 3),
            "wall_clock_elapsed_seconds": round(wall_clock_elapsed, 3),
            "average_fps_total": round(
                frame_index / total_processing_seconds if total_processing_seconds else 0.0,
                2,
            ),
            "warmup_frames_excluded": min(WARMUP_FRAMES, frame_index),
            "average_fps_after_warmup": round(
                len(stable_times) / sum(stable_times) if stable_times else 0.0, 2
            ),
            "median_frame_time_ms": round(
                statistics.median(frame_times) * 1000 if frame_times else 0.0, 2
            ),
            "p95_frame_time_ms": round(percentile(frame_times, 0.95) * 1000, 2),
        },
        "maximum_simultaneous_by_class": maximum_counts,
        "crossings": build_crossing_summary(lines, crossing_counts),
        "tracking_ids_observed": {
            "note": "Dato diagnóstico; no representa objetos únicos ni flujo real.",
            "total": sum(diagnostic_by_class.values()),
            "by_class": diagnostic_by_class,
        },
        "warning": (
            "Resultados preliminares. Las líneas requieren calibración por cámara y los cruces "
            "no están validados hasta compararlos con anotación manual."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("Proceso terminado.")
    print(f"Video: {video_path}")
    print(f"CSV: {csv_path}")
    print(f"Resumen: {summary_path}")


if __name__ == "__main__":
    main()
