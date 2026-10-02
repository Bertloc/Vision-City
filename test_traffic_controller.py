import unittest

from phase_manager import PhaseManager, PhasePriority
from traffic_light_controller import SimulationParameters, TrafficLightController
from traffic_priority import PriorityResult, PriorityScore


def priorities(a=20, b=2, demand_a=1, demand_b=1):
    return {key: PhasePriority(key, score, demand, {}, [])
            for key, score, demand in (("ns", a, demand_a), ("ew", b, demand_b))}


class ControllerTests(unittest.TestCase):
    def controller(self, **overrides):
        values = dict(min_green_seconds=3, max_green_seconds=6, yellow_seconds=2,
                      all_red_seconds=1, safe_green_seconds=4, reference_score=20,
                      starvation_wait_seconds=12)
        values.update(overrides)
        return TrafficLightController(["ns", "ew"], SimulationParameters(**values))

    def start(self, controller, scores=None, confidence="high"):
        scores = scores or priorities()
        controller.update(0, scores, confidence)
        return controller.update(1, scores, confidence)

    def test_ns_and_ew_demand(self):
        for scores, expected in ((priorities(), "ns"), (priorities(2, 20), "ew")):
            with self.subTest(expected=expected):
                result = self.start(self.controller(), scores)
                self.assertEqual(result["current_phase"], expected)
                self.assertEqual(result["current_light_state"], "GREEN")

    def test_change_during_green_respects_plan_and_minimum(self):
        controller = self.controller()
        start = self.start(controller)
        for timestamp in (2, 3, 4, 5, 6):
            result = controller.update(timestamp, priorities(0, 100))
            self.assertEqual(result["current_phase"], "ns")
            self.assertEqual(result["current_light_state"], "GREEN")
            self.assertEqual(result["planned_green"], start["planned_green"])
        self.assertEqual(controller.update(7, priorities(0, 100))["current_light_state"], "YELLOW")

    def test_maximum_and_all_transitions(self):
        controller = self.controller()
        self.assertEqual(self.start(controller, priorities(1000, 2))["planned_green"], 6)
        self.assertEqual(controller.update(7, priorities(1, 20))["current_light_state"], "YELLOW")
        self.assertEqual(controller.update(8, priorities(1, 20))["current_light_state"], "YELLOW")
        self.assertEqual(controller.update(9, priorities(1, 20))["current_light_state"], "ALL_RED")
        result = controller.update(10, priorities(1, 20))
        self.assertEqual((result["current_light_state"], result["current_phase"]), ("GREEN", "ew"))
        self.assertEqual(result["last_served_at"]["ew"], 10)

    def test_reselect_after_all_red(self):
        controller = self.controller()
        self.start(controller)
        self.assertEqual(controller.update(7, priorities(1, 20))["next_phase"], "ew")
        controller.update(9, priorities(1, 20))
        self.assertEqual(controller.update(10, priorities(20, 1))["current_phase"], "ns")

    def test_near_tie_continuity_after_clearance(self):
        controller = self.controller(starvation_wait_seconds=100)
        self.start(controller)
        controller.update(7, priorities(10, 10.5))
        controller.update(9, priorities(10, 10.5))
        result = controller.update(10, priorities(10, 10.5))
        self.assertEqual(result["current_phase"], "ns")
        self.assertIn("histéresis", result["reasons"][0])

    def test_empty_phase_and_all_empty(self):
        controller = self.controller()
        self.assertEqual(self.start(controller, priorities(0, 20, 0, 1))["current_phase"], "ew")
        controller = self.controller()
        result = self.start(controller, priorities(0, 0, 0, 0))
        self.assertEqual(result["planned_green"], 3)
        controller.update(4, priorities(0, 0, 0, 0))
        controller.update(6, priorities(0, 0, 0, 0))
        result = controller.update(7, priorities(0, 0, 0, 0))
        self.assertEqual(result["current_phase"], "ew")
        self.assertEqual(result["planned_green"], 3)

    def test_starvation_even_for_empty_phase(self):
        controller = self.controller()
        results = [controller.update(t, priorities(100000, 0, 1, 0)) for t in range(35)]
        grants = [r for r in results if r["decision"] == "INICIAR" and r["current_phase"] == "ew"]
        self.assertTrue(grants)
        self.assertEqual(grants[0]["planned_green"], 3)
        self.assertIn("Anti-starvation", grants[0]["reasons"][0])
        self.assertGreater(grants[0]["phase_priorities"]["ew"]["starvation_bonus"], 0)

    def test_low_confidence_keeps_current_then_fixed_rotation(self):
        controller = self.controller()
        self.start(controller)
        result = controller.update(2, priorities(0, 1000), "low")
        self.assertEqual(result["current_phase"], "ns")
        self.assertEqual(result["mode"], "FIXED_LOW")
        self.assertEqual(result["planned_green"], 6)
        controller.update(7, priorities(), "low")
        controller.update(9, priorities(), "low")
        result = controller.update(10, priorities(), "low")
        self.assertEqual(result["current_phase"], "ew")
        self.assertEqual(result["planned_green"], 4)

    def test_error_safe_mode_latched_and_ignores_scores(self):
        controller = self.controller()
        self.start(controller)
        result = controller.update(2, {}, "error")
        self.assertTrue(result["safe_mode"])
        self.assertEqual(result["current_light_state"], "GREEN")
        for t in range(3, 11):
            result = controller.update(t, priorities(100000, 0), "high")
        self.assertEqual(result["mode"], "SAFE_MODE")
        self.assertEqual(result["current_phase"], "ew")
        self.assertEqual(result["planned_green"], 4)
        self.assertIsNone(result["phase_priorities"]["ns"]["effective_score"])

    def test_sparse_clock_does_not_skip_clearance(self):
        controller = self.controller()
        self.start(controller)
        self.assertEqual(controller.update(100, priorities())["current_light_state"], "YELLOW")
        self.assertEqual(controller.update(101, priorities())["current_light_state"], "YELLOW")
        self.assertEqual(controller.update(102, priorities())["current_light_state"], "ALL_RED")
        with self.assertRaises(ValueError):
            controller.update(101, priorities())

    def test_no_phases_and_missing_data(self):
        controller = TrafficLightController([])
        self.assertEqual(controller.update(100, {})["current_light_state"], "ALL_RED")
        controller = self.controller()
        controller.update(0, {})
        self.assertEqual(controller.update(1, {})["mode"], "FIXED_LOW")

    def test_invalid_parameters(self):
        for values in ({"min_green_seconds": 0}, {"max_green_seconds": 1},
                       {"yellow_seconds": -1}, {"reference_score": 0},
                       {"switch_margin": float("nan")}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SimulationParameters(**values)

    def test_phase_aggregation_and_validation(self):
        phases = [{"id": "group", "name": "Grupo", "zones": ["a", "b"]}]
        manager = PhaseManager(phases, ["a", "b"])
        scores = PriorityResult(None, "tie", {
            "a": PriorityScore("a", 8, {}, []), "b": PriorityScore("b", 6, {}, [])})
        phase = manager.aggregate(scores, {"a": 3, "b": 2})["group"]
        self.assertEqual((phase.score, phase.demand), (14, 5))
        self.assertEqual(phase.components, {"a": 8, "b": 6})
        with self.assertRaises(ValueError):
            PhaseManager(phases, ["a"])
        with self.assertRaises(ValueError):
            PhaseManager(phases * 2, ["a", "b"])


if __name__ == "__main__":
    unittest.main()
