"""Prioridad explicable por zona. No decide fases ni tiempos de semáforo."""

from dataclasses import dataclass
import math

from traffic_analysis import TrafficAnalysis


@dataclass
class PriorityScore:
    zone_id: str
    score: float | None
    components: dict[str, float]
    reasons: list[str]


@dataclass
class PriorityResult:
    winner: str | None
    reason: str
    scores: dict[str, PriorityScore]


class PriorityCalculator:
    def __init__(self, current_weight=0.5, growth_weight=2.0, average_weight=1.0, tie_tolerance=0.1):
        values = (current_weight, growth_weight, average_weight, tie_tolerance)
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Pesos y tolerancia deben ser finitos y no negativos.")
        if not any(values[:3]):
            raise ValueError("Al menos un peso de prioridad debe ser positivo.")
        self.current_weight = current_weight
        self.growth_weight = growth_weight
        self.average_weight = average_weight
        self.tie_tolerance = tie_tolerance

    def calculate(self, analysis: dict[str, TrafficAnalysis]) -> PriorityResult:
        scores = {}
        for zone_id, zone in analysis.items():
            if zone.current_count is None or zone.average_count is None:
                scores[zone_id] = PriorityScore(zone_id, None, {}, ["Sin observación actual válida"])
                continue
            # La banda estable no aporta crecimiento; evita premiar ruido cercano a cero.
            growth = max(zone.growth_rate or 0, 0) if zone.trend == "growing" else 0
            components = {
                "current": zone.current_count * self.current_weight,
                "growth": growth * self.growth_weight,
                "average": zone.average_count * self.average_weight,
            }
            reasons = [
                f"{zone.current_count} vehículos presentes",
                f"Promedio reciente: {zone.average_count:.2f} vehículos",
            ]
            if zone.growth_rate is None:
                reasons.append("Historial insuficiente: sin aporte de crecimiento")
            else:
                reasons.append(f"Tendencia {zone.trend}: {zone.growth_rate:+.3f} veh/s")
            scores[zone_id] = PriorityScore(zone_id, sum(components.values()), components, reasons)
        if not scores:
            return PriorityResult(None, "no_zones", scores)
        if any(score.score is None for score in scores.values()):
            return PriorityResult(None, "missing_data", scores)
        if all(zone.current_count == 0 for zone in analysis.values()):
            return PriorityResult(None, "no_demand", scores)
        best = max(score.score for score in scores.values())
        leaders = [key for key, score in scores.items() if best - score.score <= self.tie_tolerance]
        if len(leaders) != 1:
            return PriorityResult(None, "tie", scores)
        return PriorityResult(leaders[0], "highest_score", scores)


def format_traffic_report(timestamp, analysis, priority, names):
    """Presentación fuera de app.py; conserva las razones del resultado calculado."""
    trends = {"growing": "CRECIENDO", "decreasing": "BAJANDO", "stable": "ESTABLE"}
    rows = [f"[TRAFFIC] t={timestamp:.2f}s"]
    for zone_id, zone in analysis.items():
        average = f"{zone.average_count:.2f}" if zone.average_count is not None else "N/D"
        rate = f"{zone.growth_rate:+.3f}" if zone.growth_rate is not None else "N/D"
        result = priority.scores[zone_id]
        score = f"{result.score:.2f}" if result.score is not None else "N/D"
        trend = trends[zone.trend] if zone.status == "ok" else "SIN DATOS SUFICIENTES"
        rows.append(f"{names.get(zone_id, zone_id)}: actual={zone.current_count} promedio={average} "
                    f"tendencia={trend} tasa={rate} veh/s prioridad={score}")
    if priority.winner is not None:
        rows.append(f">>> MAYOR SCORE DE ZONA (diagnóstico): {names.get(priority.winner, priority.winner)}")
        rows.extend(f"  - {reason}" for reason in priority.scores[priority.winner].reasons)
    else:
        rows.append(f">>> SIN GANADOR: {priority.reason}")
    return "\n".join(rows)
