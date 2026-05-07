"""Rate calculator for computing per-second deltas from cumulative counters."""

import time


class RateCalculator:
    """Computes per-second deltas from cumulative counter values.

    Stores previous values and timestamps to calculate rates between
    successive calls to update().
    """

    def __init__(self, key_map: dict[str, str] | None = None):
        self._prev_values: dict[str, float] | None = None
        self._prev_time: float | None = None
        self._key_map = key_map or {}

    def update(self, current_values: dict[str, float]) -> dict[str, float]:
        """Return per-second rates computed from previous values and elapsed time.

        Returns zeros on first call (no previous data) or when elapsed time
        is zero or negative.
        """
        current_time = time.time()
        zero_result = self._build_zeros(current_values)

        if self._prev_values is None or self._prev_time is None:
            self._prev_values = current_values.copy()
            self._prev_time = current_time
            return zero_result

        elapsed = current_time - self._prev_time
        if elapsed <= 0:
            return zero_result

        rates: dict[str, float] = {}
        for key, value in current_values.items():
            prev = self._prev_values.get(key, 0.0)
            output_key = self._key_map.get(key, key)
            rates[output_key] = (value - prev) / elapsed

        self._prev_values = current_values.copy()
        self._prev_time = current_time
        return rates

    def _build_zeros(self, values: dict[str, float]) -> dict[str, float]:
        """Build a zero-valued result dict with key_map applied."""
        return {self._key_map.get(k, k): 0.0 for k in values}
