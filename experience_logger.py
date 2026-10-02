"""Una experiencia por verde completo, persistida entre sesiones en JSONL."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL

from decision_evaluator import DecisionEvaluator, EvaluationParameters


class ExperienceLogger:
    def __init__(self, source_video, phases, parameters=None):
        self.parameters = parameters or EvaluationParameters()
        path = Path(self.parameters.dataset_path)
        self.path = path if path.is_absolute() else Path(__file__).resolve().parent / path
        self.session = {"session_id": uuid4().hex, "source_video": str(source_video),
                        "started_at": datetime.now(timezone.utc).isoformat()}
        self.evaluator = DecisionEvaluator(phases, self.parameters)
        self.pending = None
        self.rows = []

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a+b") as lock:
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _ids(self):
        if not self.path.exists():
            return set()
        with self.path.open(encoding="utf-8") as source:
            ids = set()
            for line in source:
                if not line.endswith("\n"):
                    raise ValueError("Dataset con última línea incompleta; revisar antes de agregar experiencias.")
                ids.add(json.loads(line)["id"])
            return ids

    def save(self, experience):
        if not self.parameters.enabled:
            return False
        if "after" not in experience or "evaluation" not in experience:
            raise ValueError("No se puede guardar una experiencia incompleta.")
        payload = json.dumps(experience, ensure_ascii=False, allow_nan=False) + "\n"
        with self._locked():
            # ponytail: escaneo O(n) bajo bloqueo; usar índice UNIQUE si el dataset crece demasiado.
            if experience["id"] in self._ids():
                return False
            with self.path.open("a", encoding="utf-8") as target:
                target.write(payload)
                target.flush()
                os.fsync(target.fileno())
        return True

    def observe(self, result, traffic_state, analysis, priority, previous, analysis_timestamp):
        if not self.parameters.enabled:
            return
        action = result["decision"]
        timestamp = result["timestamp"]
        if action == "INICIAR" and self.pending is None:
            self.pending = {
                "schema_version": 1,
                "id": uuid5(NAMESPACE_URL, f"{self.session['session_id']}:{timestamp}:{result['current_phase']}").hex,
                **self.session, "timestamp_decision": timestamp,
                "before": self._snapshot(result, traffic_state, analysis, priority, analysis_timestamp),
                "decision": {"selected_phase": result["current_phase"],
                             "planned_green_seconds": result["planned_green"],
                             "phase_score": result["phase_priorities"][result["current_phase"]]["score"],
                             "effective_score": result["phase_priorities"][result["current_phase"]]["effective_score"],
                             "reasons": result["reasons"][:],
                             "anti_starvation": any(reason.startswith("Anti-starvation:") for reason in result["reasons"]),
                             "mode": result["mode"], "adaptive_decision": result["mode"] == "ADAPTIVE"},
                "quality_reasons": [],
            }
            self.pending["before"].update(deepcopy(previous))
        if self.pending is None:
            return
        if result["confidence"] != "high":
            self.pending["quality_reasons"].append(f"Confianza {result['confidence']} durante el verde")
        if result["mode"] != "ADAPTIVE":
            self.pending["quality_reasons"].append(f"Modo {result['mode']} durante el verde")
        counts = traffic_state.vehicles_by_zone
        if any(type(counts.get(zone)) is not int or counts[zone] < 0
               for phase in self.evaluator.phases.values() for zone in phase["zones"]):
            self.pending["quality_reasons"].append("Conteos faltantes o inválidos durante el verde")
        self.pending["quality_reasons"] = list(dict.fromkeys(self.pending["quality_reasons"]))
        if action == "FINALIZAR":
            self.pending["after"] = self._snapshot(result, traffic_state, analysis, priority, analysis_timestamp)
            self.pending["after"]["elapsed_seconds"] = timestamp - self.pending["timestamp_decision"]
            self.pending["evaluation"] = self.evaluator.evaluate(self.pending)
            if self.save(self.pending):
                components = self.pending["evaluation"]["components"]
                self.rows.append({"timestamp": self.pending["timestamp_decision"],
                                  "phase": self.pending["decision"]["selected_phase"],
                                  "green_seconds": self.pending["after"]["elapsed_seconds"],
                                  "demand_before": components.get("demand_before"),
                                  "demand_after": components.get("demand_after"),
                                  "reward": self.pending["evaluation"]["reward"],
                                  "training_eligible": self.pending["evaluation"]["training_eligible"]})
            self.pending = None

    @staticmethod
    def _snapshot(result, traffic_state, analysis, priority, analysis_timestamp):
        return deepcopy({"traffic_state": asdict(traffic_state),
                         "analysis": {key: asdict(value) for key, value in analysis.items()},
                         "zone_priorities": asdict(priority),
                         "phase_priorities": result["phase_priorities"],
                         "priority_analysis_timestamp": analysis_timestamp,
                         "current_phase": result["current_phase"],
                         "current_light_state": result["current_light_state"],
                         "time_since_last_green": result["time_since_last_green"],
                         "confidence": result["confidence"], "mode": result["mode"]})

    def summary(self):
        count = 0
        if self.parameters.enabled and self.path.exists():
            with self._locked():
                count = len(self._ids())
        rewards = [row["reward"] for row in self.rows if row["reward"] is not None]
        return {**self.session, "enabled": self.parameters.enabled, "dataset_path": str(self.path),
                "generated": len(self.rows), "average_reward": sum(rewards) / len(rewards) if rewards else None,
                "dataset_count": count, "incomplete": self.pending is not None, "rows": self.rows}
