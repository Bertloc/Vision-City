import unittest

from traffic_analysis import TrafficAnalyzer
from traffic_memory import TrafficMemory
from traffic_priority import PriorityCalculator
from traffic_state import TrafficState


class AnalysisTests(unittest.TestCase):
    def analyze(self, counts, **settings):
        states = [TrafficState(float(index), {"a": count}, count) for index, count in enumerate(counts)]
        return TrafficAnalyzer(**settings).analyze(states[-1], states, ["a"])["a"]

    def test_growing_and_decreasing(self):
        growing = self.analyze([1, 2, 3, 4, 5])
        self.assertEqual((growing.current_count, growing.previous_count, growing.delta), (5, 4, 1))
        self.assertEqual((growing.average_count, growing.growth_rate, growing.trend), (3, 1, "growing"))
        falling = self.analyze([5, 4, 3, 2, 1])
        self.assertEqual((falling.growth_rate, falling.trend), (-1, "decreasing"))
        result = PriorityCalculator().calculate({"a": growing})
        self.assertEqual(result.scores["a"].components, {"current": 2.5, "growth": 2, "average": 3})
        self.assertEqual(result.scores["a"].score, 7.5)
        self.assertEqual(result.winner, "a")

    def test_small_fluctuations_and_threshold(self):
        stable = self.analyze([8, 9, 8, 9, 8, 9, 8])
        self.assertEqual(stable.trend, "stable")
        self.assertAlmostEqual(stable.growth_rate, 0)
        self.assertEqual(self.analyze([8, 9, 8, 10, 9, 11]).trend, "growing")
        neutral = self.analyze([1, 2, 3], trend_threshold=1)
        self.assertEqual(neutral.trend, "stable")
        self.assertEqual(PriorityCalculator().calculate({"a": neutral}).scores["a"].components["growth"], 0)

    def test_insufficient_history(self):
        zone = self.analyze([5])
        self.assertEqual(zone.status, "insufficient_history")
        self.assertIsNone(zone.previous_count)
        self.assertIsNone(zone.delta)
        self.assertIsNone(zone.growth_rate)
        self.assertEqual(zone.average_count, 5)
        score = PriorityCalculator().calculate({"a": zone}).scores["a"]
        self.assertEqual(score.components["growth"], 0)
        self.assertIn("insuficiente", score.reasons[-1])

    def test_window_real_timestamps_and_duplicate_current(self):
        states = [TrafficState(t, {"a": n}, n) for t, n in [(0, 100), (10, 2), (12, 4), (16, 8)]]
        result = TrafficAnalyzer().analyze(states[-1], reversed(states), ["a"])["a"]
        self.assertEqual(result.sample_count, 3)
        self.assertAlmostEqual(result.growth_rate, 1)
        self.assertEqual(result.previous_count, 4)
        self.assertEqual(result.delta, 4)

    def test_multiple_zones_empty_zone_and_tie(self):
        states = [TrafficState(t, {"a": 4, "b": 4, "empty": 0}, 8) for t in range(4)]
        analyzer = TrafficAnalyzer()
        analysis = analyzer.analyze(states[-1], states, ["a", "b", "empty"])
        result = PriorityCalculator().calculate(analysis)
        self.assertIsNone(result.winner)
        self.assertEqual(result.reason, "tie")
        self.assertEqual(result.scores["empty"].score, 0)
        analysis["b"].current_count = 3
        result = PriorityCalculator().calculate(analysis)
        self.assertEqual(result.winner, "a")
        result = PriorityCalculator(tie_tolerance=0.5).calculate(analysis)
        self.assertEqual(result.reason, "tie")

    def test_no_zones_and_all_empty(self):
        calculator = PriorityCalculator()
        self.assertEqual(calculator.calculate({}).reason, "no_zones")
        # Aunque el promedio conserve demanda pasada, no se elige si ahora todo está vacío.
        zone = self.analyze([4, 2, 0])
        result = calculator.calculate({"a": zone, "b": self.analyze([0, 0, 0])})
        self.assertIsNone(result.winner)
        self.assertEqual(result.reason, "no_demand")

    def test_missing_data_are_not_zero(self):
        states = [TrafficState(0, {"a": 4}, 4), TrafficState(1, {}, 0), TrafficState(2, {"a": 6}, 6)]
        analyzer = TrafficAnalyzer()
        zone = analyzer.analyze(states[-1], states, ["a"])["a"]
        self.assertEqual(zone.average_count, 5)
        self.assertEqual(zone.sample_count, 2)
        missing = analyzer.analyze(TrafficState(3, {}, 0), states, ["a"])
        self.assertIsNone(missing["a"].current_count)
        self.assertEqual(missing["a"].status, "missing_current")
        priority = PriorityCalculator().calculate(missing)
        self.assertEqual(priority.reason, "missing_data")
        self.assertIsNone(priority.scores["a"].score)

    def test_memory_pipeline(self):
        memory = TrafficMemory()
        for second in range(40):
            state = TrafficState(second, {"a": second}, second)
            self.assertTrue(memory.update(state))
        zone = TrafficAnalyzer().analyze(state, memory.states, ["a"])["a"]
        self.assertEqual(zone.sample_count, 9)  # Ventana inclusiva [t-8, t].
        self.assertEqual(zone.average_count, 35)
        self.assertAlmostEqual(zone.growth_rate, 1)

    def test_invalid_parameters(self):
        for settings in ({"window_seconds": 0}, {"window_seconds": 31}, {"min_samples": 1},
                         {"trend_threshold": float("nan")}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                TrafficAnalyzer(**settings)
        for settings in ({"current_weight": -1}, {"tie_tolerance": float("inf")},
                         {"current_weight": 0, "growth_weight": 0, "average_weight": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                PriorityCalculator(**settings)


if __name__ == "__main__":
    unittest.main()
