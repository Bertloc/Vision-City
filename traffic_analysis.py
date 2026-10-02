"""Tendencias por zona usando una regresión lineal sobre el historial reciente."""

from dataclasses import dataclass
import math
from statistics import mean
from typing import Iterable

from traffic_state import TrafficState


@dataclass
class TrafficAnalysis:
    current_count: int | None
    average_count: float | None
    previous_count: int | None
    delta: int | None
    trend: str
    growth_rate: float | None
    sample_count: int
    status: str


class TrafficAnalyzer:
    def __init__(self, window_seconds=8.0, min_samples=3, trend_threshold=0.1):
        if not isinstance(window_seconds, (int, float)) or not math.isfinite(window_seconds) or not 0 < window_seconds <= 30:
            raise ValueError("window_seconds debe estar entre 0 y 30 segundos.")
        if type(min_samples) is not int or not 2 <= min_samples <= 30:
            raise ValueError("min_samples debe ser un entero entre 2 y 30.")
        if not isinstance(trend_threshold, (int, float)) or not math.isfinite(trend_threshold) or trend_threshold < 0:
            raise ValueError("trend_threshold debe ser finito y no negativo.")
        self.window_seconds = window_seconds
        self.min_samples = min_samples
        self.trend_threshold = trend_threshold

    def analyze(
        self, current: TrafficState, history: Iterable[TrafficState], zone_ids: Iterable[str]
    ) -> dict[str, TrafficAnalysis]:
        if not math.isfinite(current.timestamp) or current.timestamp < 0:
            raise ValueError("El timestamp actual debe ser finito y no negativo.")
        # La memoria puede incluir ya el actual: una sola observación por timestamp.
        samples = {
            state.timestamp: state for state in history
            if current.timestamp - self.window_seconds <= state.timestamp < current.timestamp
        }
        samples[current.timestamp] = current
        ordered = sorted(samples.items())
        results = {}
        for zone_id in zone_ids:
            points = [
                (timestamp, state.vehicles_by_zone.get(zone_id))
                for timestamp, state in ordered
                if type(state.vehicles_by_zone.get(zone_id)) is int
                and state.vehicles_by_zone[zone_id] >= 0
            ]
            count = current.vehicles_by_zone.get(zone_id)
            count = count if type(count) is int and count >= 0 else None
            previous = [value for timestamp, value in points if timestamp < current.timestamp]
            previous_count = previous[-1] if previous else None
            average = mean(value for _, value in points) if points else None
            rate = None
            status = "missing_current" if count is None else "insufficient_history"
            if count is not None and len(points) >= self.min_samples:
                # Centrar tiempos evita pérdida de precisión con timestamps grandes.
                time_mean = mean(timestamp for timestamp, _ in points)
                denominator = sum((timestamp - time_mean) ** 2 for timestamp, _ in points)
                rate = sum((timestamp - time_mean) * (value - average) for timestamp, value in points) / denominator
                status = "ok"
            trend = "stable"
            if rate is not None and abs(rate) > self.trend_threshold:
                trend = "growing" if rate > 0 else "decreasing"
            results[zone_id] = TrafficAnalysis(
                count, average, previous_count,
                count - previous_count if count is not None and previous_count is not None else None,
                trend, rate, len(points), status,
            )
        return results
