import unittest

from traffic_memory import TrafficMemory
from traffic_state import TrafficState, bottom_center, count_vehicles_by_zone, validate_waiting_zones


class TrafficTests(unittest.TestCase):
    def setUp(self):
        self.zones = [{"id": "lane", "name": "Carril", "points": [
            [0.25, 0.5], [0.75, 0.5], [0.75, 1], [0.25, 1],
        ]}]

    def test_presence_boundary_duplicates_exit_and_resolution(self):
        validate_waiting_zones(self.zones)
        point = bottom_center((25, 10, 75, 75), 100, 100)
        self.assertEqual(point, bottom_center((50, 20, 150, 150), 200, 200))
        state = count_vehicles_by_zone(0, [(1, point), (1, point), (2, (0.25, 0.5)),
                                             (3, (0.1, 0.1))], self.zones)
        self.assertEqual(state.vehicles_by_zone, {"lane": 2})
        self.assertEqual(state.total_vehicles, 2)
        self.assertEqual(count_vehicles_by_zone(1, [(1, (0, 0))], self.zones).total_vehicles, 0)
        self.assertEqual(count_vehicles_by_zone(2, [], self.zones).vehicles_by_zone, {"lane": 0})
        overlap = self.zones + [dict(self.zones[0], id="other")]
        self.assertEqual(count_vehicles_by_zone(0, [(1, point)], overlap).total_vehicles, 1)
        self.assertEqual(count_vehicles_by_zone(0, [(1, point)], []).vehicles_by_zone, {})

    def test_concave_polygon(self):
        zones = [{"id": "L", "name": "L", "points": [
            [0, 0], [1, 0], [1, 0.25], [0.25, 0.25], [0.25, 1], [0, 1],
        ]}]
        validate_waiting_zones(zones)
        self.assertEqual(count_vehicles_by_zone(0, [(1, (0.5, 0.5)), (2, (0.1, 0.5))], zones).total_vehicles, 1)

    def test_invalid_zones(self):
        for points in ([], [[0, 0], [1, 1]], [[0, 0], [1, 1], [2, 0]],
                       [[0, 0], [0.5, 0.5], [1, 1]], [[0, 0], [1, 0], [0, float("nan")]]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                validate_waiting_zones([dict(self.zones[0], points=points)])
        with self.assertRaises(ValueError):
            validate_waiting_zones(self.zones * 2)

    def test_sampling_expiry_and_snapshot(self):
        memory = TrafficMemory()
        state = TrafficState(0, {"lane": 1}, 1)
        self.assertTrue(memory.update(state))
        state.vehicles_by_zone["lane"] = 99
        self.assertEqual(memory.states[0].vehicles_by_zone["lane"], 1)
        self.assertFalse(memory.update(TrafficState(0.9, {}, 0)))
        for second in range(1, 36):
            self.assertTrue(memory.update(TrafficState(second, {}, 0)))
        self.assertEqual(len(memory.states), 30)
        self.assertEqual(memory.states[0].timestamp, 6)
        memory.update(TrafficState(70, {}, 0))
        self.assertEqual(len(memory.states), 1)
        with self.assertRaises(ValueError):
            memory.update(TrafficState(69, {}, 0))


if __name__ == "__main__":
    unittest.main()
