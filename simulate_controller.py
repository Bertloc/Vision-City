"""Escenarios ficticios reproducibles; no importa ni ejecuta YOLO."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from phase_manager import PhaseManager
from traffic_analysis import TrafficAnalyzer
from traffic_light_controller import SimulationParameters, TrafficLightController, format_decision
from traffic_memory import TrafficMemory
from traffic_priority import PriorityCalculator
from traffic_state import TrafficState


def simulate(config):
    zones = config["zone_ids"]
    manager = PhaseManager(config["traffic_phases"], zones)
    controller = TrafficLightController(manager.phases, SimulationParameters(**config.get("simulation_parameters", {})))
    memory = TrafficMemory()
    analyzer = TrafficAnalyzer(**config.get("traffic_analysis", {}))
    calculator = PriorityCalculator(**config.get("traffic_priority", {}))
    events = config["events"]
    if not events or events[0]["timestamp"] != 0 or any(
        after["timestamp"] <= before["timestamp"] for before, after in zip(events, events[1:])
    ):
        raise ValueError("events debe empezar en t=0 y estar ordenado sin timestamps repetidos.")
    index = 0
    for second in range(config["duration_seconds"] + 1):
        while index + 1 < len(events) and events[index + 1]["timestamp"] <= second:
            index += 1
        event = events[index]
        counts = event["counts"].copy()
        state = TrafficState(second, counts, sum(counts.values()))
        memory.update(state)
        analysis = analyzer.analyze(state, memory.states, zones)
        priority = calculator.calculate(analysis)
        phases = manager.aggregate(priority, counts)
        decision = controller.update(second, phases, event.get("confidence", "high"))
        yield {**asdict(state), "analysis": {key: asdict(value) for key, value in analysis.items()},
               "priority": asdict(priority), **decision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/simulation.json")
    parser.add_argument("--output", default="output/simulation.jsonl")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    names = {phase["id"]: phase["name"] for phase in config["traffic_phases"]}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for result in simulate(config):
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            print(format_decision(result, names))
    print(f"Simulación ficticia guardada en {path}")


if __name__ == "__main__":
    main()
