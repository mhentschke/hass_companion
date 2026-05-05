"""Unit tests for RateCalculator."""

from unittest.mock import patch

from core.rate import RateCalculator


class TestRateCalculator:
    def test_first_call_returns_zeros(self):
        calc = RateCalculator()
        result = calc.update({"read_count": 100.0, "write_count": 50.0})
        assert result == {"read_count": 0.0, "write_count": 0.0}

    def test_subsequent_call_returns_correct_rates(self):
        calc = RateCalculator()
        with patch("core.rate.time.time", return_value=1000.0):
            calc.update({"bytes": 100.0, "packets": 10.0})
        with patch("core.rate.time.time", return_value=1002.0):
            result = calc.update({"bytes": 200.0, "packets": 20.0})
        assert result["bytes"] == 50.0  # (200-100) / 2s
        assert result["packets"] == 5.0  # (20-10) / 2s

    def test_zero_elapsed_time_returns_zeros(self):
        calc = RateCalculator()
        with patch("core.rate.time.time", return_value=1000.0):
            calc.update({"x": 10.0})
        with patch("core.rate.time.time", return_value=1000.0):
            result = calc.update({"x": 20.0})
        assert result == {"x": 0.0}

    def test_key_map_renames_output_keys(self):
        key_map = {"read_count": "read_rate", "write_count": "write_rate"}
        calc = RateCalculator(key_map=key_map)
        with patch("core.rate.time.time", return_value=1000.0):
            result = calc.update({"read_count": 100.0, "write_count": 50.0})
        # First call returns zeros with mapped keys
        assert result == {"read_rate": 0.0, "write_rate": 0.0}

        with patch("core.rate.time.time", return_value=1001.0):
            result = calc.update({"read_count": 110.0, "write_count": 55.0})
        assert result["read_rate"] == 10.0  # (110-100) / 1s
        assert result["write_rate"] == 5.0  # (55-50) / 1s
