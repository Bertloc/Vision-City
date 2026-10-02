"""Agrupa prioridades; la compatibilidad de movimientos la define la configuración."""

from dataclasses import dataclass
import math

from traffic_priority import PriorityResult


@dataclass
class PhasePriority:
    phase_id: str
    score: float | None
    demand: int | None
    components: dict[str, float | None]
    reasons: list[str]


class PhaseManager:
    def __init__(self, phases, zone_ids):
        if not isinstance(phases, list):
            raise ValueError("traffic_phases debe ser una lista.")
        self.phases = {}
        known = set(zone_ids)
        for phase in phases:
            if not isinstance(phase, dict):
                raise ValueError("Cada fase debe ser un objeto.")
            phase_id, name, zones = phase.get("id"), phase.get("name"), phase.get("zones")
            if not isinstance(phase_id, str) or not phase_id.strip() or phase_id in self.phases:
                raise ValueError("Las fases requieren IDs únicos no vacíos.")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Cada fase requiere un nombre.")
            if (not isinstance(zones, list) or not zones
                    or any(not isinstance(zone, str) or zone not in known for zone in zones)
                    or len(set(zones)) != len(zones)):
                raise ValueError(f"Fase {phase_id}: zonas desconocidas, repetidas o vacías.")
            self.phases[phase_id] = {"id": phase_id, "name": name, "zones": list(zones)}

    def aggregate(self, priorities: PriorityResult, counts) -> dict[str, PhasePriority]:
        results = {}
        for phase_id, phase in self.phases.items():
            components = {}
            for zone in phase["zones"]:
                result = priorities.scores.get(zone)
                score = result.score if result else None
                components[zone] = score if score is not None and math.isfinite(score) and score >= 0 else None
            demand = [counts.get(zone) for zone in phase["zones"]]
            valid = all(value is not None for value in components.values())
            valid_counts = all(type(value) is int and value >= 0 for value in demand)
            results[phase_id] = PhasePriority(
                phase_id, sum(components.values()) if valid else None,
                sum(demand) if valid_counts else None, components,
                [f"{zone}: {score if score is not None else 'sin datos'}" for zone, score in components.items()],
            )
        return results
