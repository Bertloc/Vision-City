"""Ocupación actual de zonas; independiente del conteo histórico de cruces."""

from dataclasses import dataclass
from typing import Any, Iterable

import cv2
import numpy as np

VEHICLE_CLASSES = {2, 3, 5, 7}  # COCO: car, motorcycle, bus, truck.


@dataclass
class TrafficState:
    timestamp: float  # Segundos desde el inicio de la fuente, no hora de procesamiento.
    vehicles_by_zone: dict[str, int]
    total_vehicles: int  # IDs únicos dentro de la unión de las zonas.


def validate_waiting_zones(zones: Any) -> None:
    if not isinstance(zones, list):
        raise ValueError("waiting_zones debe ser una lista.")
    seen = set()
    for zone in zones:
        if not isinstance(zone, dict):
            raise ValueError("Cada waiting_zone debe ser un objeto.")
        zone_id = zone.get("id")
        if not isinstance(zone_id, str) or not zone_id.strip() or zone_id in seen:
            raise ValueError("waiting_zones requiere IDs únicos no vacíos.")
        seen.add(zone_id)
        if not isinstance(zone.get("name"), str) or not zone["name"].strip():
            raise ValueError(f"Zona {zone_id}: name debe ser texto no vacío.")
        points = zone.get("points")
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"Zona {zone_id}: se necesitan al menos tres vértices.")
        for point in points:
            if not isinstance(point, list) or len(point) != 2 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1
                for v in point
            ):
                raise ValueError(f"Zona {zone_id}: puntos numéricos [x, y] entre 0 y 1.")
        if len(set(map(tuple, points))) != len(points) or cv2.contourArea(
            np.array(points, dtype=np.float32)
        ) == 0:
            raise ValueError(f"Zona {zone_id}: vértices repetidos o polígono sin área.")


def bottom_center(box: Iterable[float], width: int, height: int) -> tuple[float, float]:
    x1, _, x2, y2 = box
    # El borde inferior aproxima el contacto del vehículo con el pavimento.
    return (x1 + x2) / (2 * width), y2 / height


def count_vehicles_by_zone(
    timestamp: float,
    vehicles: Iterable[tuple[int, tuple[float, float]]],
    zones: list[dict[str, Any]],
) -> TrafficState:
    contours = {
        zone["id"]: np.array(zone["points"], dtype=np.float32) for zone in zones
    }
    members: dict[str, set[int]] = {zone_id: set() for zone_id in contours}
    # Cada llamada empieza vacía: un vehículo que salió deja de contarse.
    for track_id, point in dict(vehicles).items():
        for zone_id, contour in contours.items():
            if cv2.pointPolygonTest(contour, point, False) >= 0:  # Incluye el borde.
                members[zone_id].add(track_id)
    return TrafficState(
        timestamp,
        {zone_id: len(ids) for zone_id, ids in members.items()},
        len(set().union(*members.values())),
    )
