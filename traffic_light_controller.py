"""Semáforo exclusivamente virtual, dirigido por timestamps de la fuente."""

from dataclasses import asdict, dataclass
import math

from phase_manager import PhasePriority


@dataclass
class SimulationParameters:
    min_green_seconds: float = 10.0
    max_green_seconds: float = 40.0
    yellow_seconds: float = 3.0
    all_red_seconds: float = 2.0
    reference_score: float = 30.0
    switch_margin: float = 1.0
    starvation_wait_seconds: float = 60.0
    starvation_bonus_per_second: float = 1.0
    safe_green_seconds: float = 15.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"simulation_parameters.{key}: número finito no negativo requerido.")
        for key in ("min_green_seconds", "yellow_seconds", "all_red_seconds", "reference_score", "starvation_wait_seconds"):
            if getattr(self, key) <= 0:
                raise ValueError(f"simulation_parameters.{key} debe ser positivo.")
        if not self.min_green_seconds <= self.safe_green_seconds <= self.max_green_seconds:
            raise ValueError("Se requiere min_green <= safe_green <= max_green.")


class TrafficLightController:
    def __init__(self, phase_ids, parameters=None):
        self.phase_ids = list(phase_ids)
        if len(set(self.phase_ids)) != len(self.phase_ids):
            raise ValueError("IDs de fase repetidos.")
        self.parameters = parameters or SimulationParameters()
        self.current_phase = None
        self.current_state = "ALL_RED"
        self.state_started_at = None
        self.green_started_at = None
        self.planned_green_duration = 0.0
        self.next_phase = None
        self.last_served_at = dict.fromkeys(self.phase_ids)
        self.waiting_since = dict.fromkeys(self.phase_ids)
        self.safe_mode = False
        self._last_timestamp = -1.0

    def _cycle_next(self):
        if self.current_phase is None:
            return self.phase_ids[0]
        return self.phase_ids[(self.phase_ids.index(self.current_phase) + 1) % len(self.phase_ids)]

    def _rank(self, timestamp, priorities, adaptive):
        ranked = {}
        for phase_id in self.phase_ids:
            phase = priorities.get(phase_id)
            start = self.waiting_since[phase_id]
            waiting = timestamp - start if start is not None else 0.0
            bonus = max(0, waiting - self.parameters.starvation_wait_seconds) * self.parameters.starvation_bonus_per_second if adaptive else 0.0
            score = phase.score if phase else None
            ranked[phase_id] = {
                "score": score,
                "demand": phase.demand if phase else None,
                "components": phase.components if phase else {},
                "reasons": (phase.reasons[:] if phase else ["Sin datos"])
                    + ([f"Bonus por espera: +{bonus:.2f}"] if bonus else []),
                "waiting_seconds": waiting,
                "starvation_bonus": bonus,
                "effective_score": score + bonus if score is not None and adaptive else None,
            }
        return ranked

    def _select(self, ranked, adaptive):
        if not adaptive:
            return self._cycle_next(), "Rotación fija: confianza insuficiente; sin scores adaptativos"
        overdue = [key for key in self.phase_ids if ranked[key]["waiting_seconds"] >= self.parameters.starvation_wait_seconds]
        if overdue:
            selected = max(overdue, key=lambda key: ranked[key]["waiting_seconds"])
            return selected, "Anti-starvation: fase con mayor espera vencida (orden configurado si empatan)"
        candidates = [key for key in self.phase_ids if ranked[key]["demand"] > 0]
        if not candidates:
            return self._cycle_next(), "Sin demanda: rotación fija con verde mínimo"
        best = max(candidates, key=lambda key: ranked[key]["effective_score"])
        if self.current_phase in candidates and ranked[best]["effective_score"] - ranked[self.current_phase]["effective_score"] <= self.parameters.switch_margin:
            return self.current_phase, "Margen de histéresis: continuidad tras el despeje"
        close = [key for key in candidates if ranked[best]["effective_score"] - ranked[key]["effective_score"] <= self.parameters.switch_margin]
        selected = max(close, key=lambda key: ranked[key]["waiting_seconds"])
        return selected, "Prioridad de fase; scores cercanos se resuelven por espera y orden configurado"

    def update(self, timestamp: float, priorities: dict[str, PhasePriority], confidence="high"):
        if not math.isfinite(timestamp) or timestamp < 0 or timestamp < self._last_timestamp:
            raise ValueError("timestamp debe ser finito, no negativo y no decreciente.")
        if confidence not in ("high", "low", "error"):
            raise ValueError("confidence debe ser high, low o error.")
        self._last_timestamp = timestamp
        if self.state_started_at is None:
            self.state_started_at = timestamp
            self.waiting_since = dict.fromkeys(self.phase_ids, timestamp)
        if confidence == "error":
            self.safe_mode = True  # Enclavado hasta reiniciar; no oscila con la señal de confianza.
        valid = all(
            key in priorities and priorities[key].score is not None
            and math.isfinite(priorities[key].score) and priorities[key].score >= 0
            and type(priorities[key].demand) is int and priorities[key].demand >= 0
            for key in self.phase_ids
        )
        adaptive = confidence == "high" and valid and not self.safe_mode
        reasons = []
        if self.safe_mode:
            reasons.append("SAFE_MODE: pérdida de confianza; rotación fija hasta reiniciar")
        elif not adaptive:
            reasons.append("Confianza baja o datos faltantes: conservar verde vigente; después rotación fija")
        ranked = self._rank(timestamp, priorities, adaptive)
        elapsed = timestamp - self.state_started_at
        action = "MANTENER"
        if not self.phase_ids:
            reasons.append("Sin fases configuradas: permanecer en ALL_RED")
        elif self.current_state == "GREEN":
            if elapsed >= self.planned_green_duration:
                self.current_state = "YELLOW"
                self.state_started_at = timestamp
                self.waiting_since[self.current_phase] = timestamp
                self.next_phase, reason = self._select(ranked, adaptive)
                action = "FINALIZAR"
                reasons.extend(["Verde planificado completado; mínimo cumplido", reason,
                                "Siguiente fase provisional; se reevaluará al terminar ALL_RED"])
            else:
                remaining = self.planned_green_duration - elapsed
                reasons.extend([
                    "min_green cumplido" if elapsed >= self.parameters.min_green_seconds else "min_green pendiente",
                    f"Conservar el plan: quedan {remaining:.2f} s de verde",
                ])
        elif self.current_state == "YELLOW":
            if elapsed >= self.parameters.yellow_seconds:
                self.current_state = "ALL_RED"
                self.state_started_at = timestamp
                action = "DESPEJAR"
            reasons.append("Respetar amarillo y TODO-ROJO antes del siguiente verde")
        elif elapsed >= self.parameters.all_red_seconds:
            selected, reason = self._select(ranked, adaptive)
            phase = priorities.get(selected)
            if not adaptive:
                duration = self.parameters.safe_green_seconds
            else:
                demand = min(1.0, phase.score / self.parameters.reference_score) if phase.demand else 0.0
                duration = self.parameters.min_green_seconds + demand * (
                    self.parameters.max_green_seconds - self.parameters.min_green_seconds
                )
            self.current_phase = selected
            self.current_state = "GREEN"
            self.state_started_at = self.green_started_at = timestamp
            self.planned_green_duration = duration
            self.last_served_at[selected] = timestamp
            self.waiting_since[selected] = None
            self.next_phase = None
            action = "INICIAR"
            reasons.extend([reason, f"Verde fijado al inicio: {duration:.2f} s"])
        else:
            reasons.append("Completar TODO-ROJO inicial o entre fases")

        # Una llamada avanza como máximo una transición: nunca omite despejes por un salto de reloj.
        state_duration = {
            "GREEN": self.planned_green_duration,
            "YELLOW": self.parameters.yellow_seconds,
            "ALL_RED": self.parameters.all_red_seconds,
        }[self.current_state]
        return {
            "timestamp": timestamp,
            "phase_priorities": ranked,
            "current_phase": self.current_phase,
            "current_light_state": self.current_state,
            "state_started_at": self.state_started_at,
            "green_started_at": self.green_started_at,
            "planned_green": self.planned_green_duration,
            "elapsed_state_time": timestamp - self.state_started_at,
            "remaining_seconds": max(0, state_duration - (timestamp - self.state_started_at)),
            "next_phase": self.next_phase,
            "decision": action,
            "reasons": reasons,
            "safe_mode": self.safe_mode,
            "mode": "SAFE_MODE" if self.safe_mode else "ADAPTIVE" if adaptive else "FIXED_LOW",
            "confidence": confidence,
            "last_served_at": self.last_served_at.copy(),
            "waiting_since": self.waiting_since.copy(),
            "time_since_last_green": {
                key: (0.0 if key == self.current_phase and self.current_state == "GREEN"
                      else timestamp - value if value is not None else None)
                for key, value in self.last_served_at.items()
            },
        }


def format_decision(result, names):
    phase = names.get(result["current_phase"], "ninguna")
    scores = " | ".join(f"{names[key]}: {value['effective_score']}" for key, value in result["phase_priorities"].items())
    return (f"[DECISION] t={result['timestamp']:.2f}s fase={phase} "
            f"estado={result['current_light_state']} modo={result['mode']} "
            f"transcurrido={result['elapsed_state_time']:.2f}s verde={result['planned_green']:.2f}s\n"
            f"Fases: {scores}\n{result['decision']} | siguiente={result['next_phase']}\n"
            + "\n".join(f"- {reason}" for reason in result["reasons"]))
