"""Evaluación explicable de ocupación; no mide throughput ni entrena modelos."""

from dataclasses import asdict, dataclass
import math


@dataclass
class EvaluationParameters:
    enabled: bool = True
    dataset_path: str = "data/experience/experiences.jsonl"
    demand_reduction_weight: float = 1.0
    other_growth_penalty: float = 1.0

    def __post_init__(self):
        if type(self.enabled) is not bool or not isinstance(self.dataset_path, str) or not self.dataset_path.strip():
            raise ValueError("experience_evaluation: enabled booleano y dataset_path no vacío requeridos.")
        for key in ("demand_reduction_weight", "other_growth_penalty"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"experience_evaluation.{key}: número finito no negativo requerido.")


class DecisionEvaluator:
    def __init__(self, phases, parameters=None):
        self.phases = phases
        self.parameters = parameters or EvaluationParameters()

    def evaluate(self, experience):
        before, after = experience["before"], experience["after"]
        selected = experience["decision"]["selected_phase"]
        served = set(self.phases[selected]["zones"])
        other = set().union(*(set(phase["zones"]) for phase in self.phases.values())) - served
        counts_before = before["traffic_state"]["vehicles_by_zone"]
        counts_after = after["traffic_state"]["vehicles_by_zone"]
        reasons = list(experience["quality_reasons"])
        if not experience["decision"]["adaptive_decision"]:
            reasons.append("Decisión no adaptativa")
        if any(type(counts.get(zone)) is not int or counts[zone] < 0
               for counts in (counts_before, counts_after) for zone in served | other):
            reasons.append("Conteos faltantes o inválidos")
        weights = {key: value for key, value in asdict(self.parameters).items() if key.endswith(("weight", "penalty"))}
        if reasons:
            return {"reward": None, "components": {}, "weights": weights,
                    "training_eligible": False, "reasons": list(dict.fromkeys(reasons))}
        reduction = sum(counts_before[zone] - counts_after[zone] for zone in served)
        growth = sum(max(0, counts_after[zone] - counts_before[zone]) for zone in other)
        return {
            "reward": reduction * self.parameters.demand_reduction_weight - growth * self.parameters.other_growth_penalty,
            "components": {"demand_before": sum(counts_before[zone] for zone in served),
                           "demand_after": sum(counts_after[zone] for zone in served),
                           "demand_reduction": reduction, "other_zone_growth": growth},
            "weights": weights, "training_eligible": True,
            "reasons": ["Reducción de ocupación en zonas atendidas", "Penalización del crecimiento positivo por zona no atendida"],
        }
