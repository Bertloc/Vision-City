import json
from pathlib import Path
import tempfile
import unittest

from decision_evaluator import EvaluationParameters
from experience_logger import ExperienceLogger
from phase_manager import PhaseManager
from traffic_analysis import TrafficAnalyzer
from traffic_light_controller import SimulationParameters, TrafficLightController
from traffic_priority import PriorityCalculator
from traffic_state import TrafficState


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "experiences.jsonl"
        self.phases = PhaseManager([
            {"id": "ns", "name": "NS", "zones": ["n"]},
            {"id": "ew", "name": "EW", "zones": ["e"]}], ["n", "e"])
        self.logger = self.new_logger()
        self.controller = TrafficLightController(self.phases.phases, SimulationParameters(
            min_green_seconds=1, max_green_seconds=1, safe_green_seconds=1,
            yellow_seconds=1, all_red_seconds=1))

    def new_logger(self):
        return ExperienceLogger("video.mp4", self.phases.phases,
                                EvaluationParameters(dataset_path=str(self.path)))

    def tick(self, timestamp, n=10, e=2, confidence="high"):
        state = TrafficState(timestamp, {"n": n, "e": e}, n + e)
        analysis = TrafficAnalyzer().analyze(state, [], ["n", "e"])
        priority = PriorityCalculator().calculate(analysis)
        phases = self.phases.aggregate(priority, state.vehicles_by_zone)
        previous = {"current_phase": self.controller.current_phase,
                    "current_light_state": self.controller.current_state}
        result = self.controller.update(timestamp, phases, confidence)
        self.logger.observe(result, state, analysis, priority, previous, timestamp)
        return result

    def complete(self, n=4, e=2, confidence="high"):
        self.tick(0, confidence=confidence)
        self.tick(1, confidence=confidence)
        self.tick(2, n, e, confidence)
        return json.loads(self.path.read_text(encoding="utf-8").splitlines()[-1])

    def test_open_at_green_and_snapshot_is_independent(self):
        self.tick(0)
        self.assertIsNone(self.logger.pending)
        self.assertEqual(self.tick(1)["decision"], "INICIAR")
        self.assertEqual(self.logger.pending["before"]["current_light_state"], "ALL_RED")
        self.assertEqual(self.logger.pending["before"]["traffic_state"]["vehicles_by_zone"]["n"], 10)
        self.assertFalse(self.path.exists())

    def test_close_at_yellow_reduction_and_positive_reward(self):
        record = self.complete()
        self.assertIsNone(self.logger.pending)
        self.assertEqual(record["after"]["current_light_state"], "YELLOW")
        self.assertEqual(record["after"]["elapsed_seconds"], 1)
        self.assertEqual(record["evaluation"]["components"]["demand_reduction"], 6)
        self.assertEqual(record["evaluation"]["reward"], 6)
        self.assertTrue(record["evaluation"]["training_eligible"])

    def test_other_growth_penalty_and_negative_reward(self):
        record = self.complete(n=9, e=6)
        self.assertEqual(record["evaluation"]["components"]["other_zone_growth"], 4)
        self.assertEqual(record["evaluation"]["reward"], -3)

    def test_weights_configurable(self):
        self.logger.parameters.demand_reduction_weight = 2
        self.logger.parameters.other_growth_penalty = 3
        self.assertEqual(self.complete(n=8, e=3)["evaluation"]["reward"], 1)

    def test_append_sessions_preserves_original_and_rejects_duplicates(self):
        record = self.complete()
        original = self.path.read_bytes()
        other = self.new_logger()
        self.assertNotEqual(other.session["session_id"], record["session_id"])
        self.assertFalse(other.save(record))
        record2 = dict(record, id="another", **other.session)
        self.assertTrue(other.save(record2))
        self.assertTrue(self.path.read_bytes().startswith(original))
        self.assertEqual(other.summary()["dataset_count"], 2)

    def test_low_confidence_not_eligible(self):
        record = self.complete(confidence="low")
        self.assertFalse(record["decision"]["adaptive_decision"])
        self.assertFalse(record["evaluation"]["training_eligible"])
        self.assertIsNone(record["evaluation"]["reward"])
        self.assertTrue(any("low" in reason for reason in record["quality_reasons"]))

    def test_safe_mode_not_eligible(self):
        record = self.complete(confidence="error")
        self.assertEqual(record["decision"]["mode"], "SAFE_MODE")
        self.assertFalse(record["decision"]["adaptive_decision"])
        self.assertFalse(record["evaluation"]["training_eligible"])

    def test_low_mid_green_remains_flagged_after_recovery(self):
        self.tick(0)
        self.tick(1)
        self.tick(1.5, confidence="low")
        self.tick(2)
        record = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(record["decision"]["adaptive_decision"])
        self.assertFalse(record["evaluation"]["training_eligible"])

    def test_incomplete_not_saved(self):
        self.tick(0)
        self.tick(1)
        self.assertTrue(self.logger.summary()["incomplete"])
        self.assertEqual(self.logger.summary()["generated"], 0)
        self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError):
            self.logger.save(self.logger.pending)

    def test_repeated_end_event_does_not_duplicate(self):
        self.complete()
        self.tick(2)
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(self.logger.summary()["generated"], 1)

    def test_disabled_does_not_write(self):
        self.logger.parameters.enabled = False
        self.tick(0)
        self.tick(1)
        self.tick(2)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.logger.summary()["generated"], 0)

    def test_corrupt_dataset_fails_without_overwriting(self):
        record = self.complete()
        self.path.write_text("invalid\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.new_logger().save(record)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "invalid\n")

    def test_missing_counts_not_eligible(self):
        record = self.complete()
        record["after"]["traffic_state"]["vehicles_by_zone"].pop("e")
        result = self.logger.evaluator.evaluate(record)
        self.assertFalse(result["training_eligible"])
        self.assertIsNone(result["reward"])

    def test_other_zones_not_double_counted_or_net_cancelled(self):
        record = self.complete(n=8, e=5)
        self.logger.evaluator.phases = {
            **self.phases.phases, "duplicate": {"zones": ["e", "x"]}}
        record["before"]["traffic_state"]["vehicles_by_zone"]["x"] = 10
        record["after"]["traffic_state"]["vehicles_by_zone"]["x"] = 0
        self.assertEqual(self.logger.evaluator.evaluate(record)["reward"], -1)

    def test_invalid_parameters(self):
        for options in ({"enabled": 1}, {"dataset_path": ""},
                        {"other_growth_penalty": -1}, {"demand_reduction_weight": float("nan")}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                EvaluationParameters(**options)


if __name__ == "__main__":
    unittest.main()
