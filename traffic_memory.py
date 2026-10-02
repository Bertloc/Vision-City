"""Una muestra por segundo y una ventana temporal de hasta 30 segundos."""

import math
from collections import deque
from copy import deepcopy

from traffic_state import TrafficState


class TrafficMemory:
    def __init__(self) -> None:
        self.states: deque[TrafficState] = deque(maxlen=30)
        self._last_timestamp = -1.0
        self._last_second = -1

    def update(self, state: TrafficState) -> bool:
        timestamp = state.timestamp
        if not math.isfinite(timestamp) or timestamp < 0 or timestamp < self._last_timestamp:
            raise ValueError("timestamp debe ser finito, no negativo y no decreciente.")
        self._last_timestamp = timestamp
        while self.states and timestamp - self.states[0].timestamp >= 30:
            self.states.popleft()
        second = math.floor(timestamp)
        if second == self._last_second:
            return False
        # No inventamos muestras intermedias si la fuente salta varios segundos.
        self.states.append(deepcopy(state))
        self._last_second = second
        return True
