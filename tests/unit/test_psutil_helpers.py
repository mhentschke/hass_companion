"""Unit tests for psutil helper functions in core.psutil_bindings."""

import re
import pytest

from core.psutil_bindings import dict_unit_convert, dict_round, flatten_dict, filter_dict


# --- dict_unit_convert ---

class TestDictUnitConvert:
    def test_subset_of_keys_converted(self):
        d = {"bytes_sent": 1024, "bytes_recv": 2048, "packets": 10}
        result = dict_unit_convert(d, 0.001, ["bytes_sent", "bytes_recv"])
        assert result["bytes_sent"] == 1024 * 0.001
        assert result["bytes_recv"] == 2048 * 0.001
        assert result["packets"] == 10  # untouched

    def test_missing_keys_ignored(self):
        d = {"a": 100}
        result = dict_unit_convert(d, 2, ["a", "b", "c"])
        assert result["a"] == 200
        assert "b" not in result

    def test_empty_dict(self):
        result = dict_unit_convert({}, 10, ["x"])
        assert result == {}

    def test_no_keys_specified_converts_all(self):
        d = {"x": 10, "y": 20}
        result = dict_unit_convert(d, 0.5)
        assert result["x"] == 5.0
        assert result["y"] == 10.0


# --- dict_round ---

class TestDictRound:
    def test_float_precision(self):
        d = {"temp": 3.14159, "humidity": 72.666}
        result = dict_round(d, ["temp", "humidity"], 2)
        assert result["temp"] == 3.14
        assert result["humidity"] == 72.67

    def test_nested_dict_rounded(self):
        d = {"inner": {"val": 1.23456}}
        result = dict_round(d, ["inner"], 2)
        assert result["inner"]["val"] == 1.23

    def test_non_float_values_unchanged(self):
        d = {"count": 5, "name": "test", "rate": 1.555}
        result = dict_round(d, ["count", "name", "rate"], 1)
        assert result["count"] == 5
        assert result["name"] == "test"
        assert result["rate"] == 1.6


# --- flatten_dict ---

class TestFlattenDict:
    def test_nested_dict_flattened(self):
        d = {"disk0": {"read": 100, "write": 200}, "disk1": {"read": 50, "write": 75}}
        result = flatten_dict(d)
        assert result["disk0:read"] == 100
        assert result["disk0:write"] == 200
        assert result["disk1:read"] == 50
        assert "disk0" not in result

    def test_already_flat_unchanged(self):
        d = {"a": 1, "b": 2}
        result = flatten_dict(d)
        assert result == {"a": 1, "b": 2}

    def test_custom_separator(self):
        d = {"net": {"sent": 10, "recv": 20}}
        result = flatten_dict(d, separator=".")
        assert result["net.sent"] == 10
        assert result["net.recv"] == 20


# --- filter_dict ---

class TestFilterDict:
    def test_include_patterns_match(self):
        d = {"sda": 1, "sdb": 2, "nvme0n1": 3}
        result = filter_dict(d, include=["sd.*"])
        assert "sda" in result
        assert "sdb" in result
        assert "nvme0n1" not in result

    def test_exclude_patterns_filter(self):
        d = {"sda": 1, "sdb": 2, "loop0": 3, "loop1": 4}
        result = filter_dict(d, exclude=["loop.*"])
        assert "sda" in result
        assert "sdb" in result
        assert "loop0" not in result
        assert "loop1" not in result

    def test_both_empty_returns_all(self):
        d = {"a": 1, "b": 2, "c": 3}
        result = filter_dict(d, include=[], exclude=[])
        assert result == d


# --- net_io_counters_total ---

class TestNetIOCountersTotal:
    def test_returns_expected_keys(self):
        from core.psutil_bindings import net_io_counters_total
        result = net_io_counters_total()
        expected_keys = {"bytes_sent", "bytes_recv", "packets_sent", "packets_recv", "errin", "errout", "dropin", "dropout"}
        assert expected_keys == set(result.keys())

    def test_values_are_numeric(self):
        from core.psutil_bindings import net_io_counters_total
        result = net_io_counters_total()
        for v in result.values():
            assert isinstance(v, (int, float))


# --- net_io_counters_per_nic ---

class TestNetIOCountersPerNic:
    def test_returns_flattened_keys(self):
        from core.psutil_bindings import net_io_counters_per_nic
        result = net_io_counters_per_nic()
        # Should have nic:metric format keys
        assert len(result) > 0
        for key in result.keys():
            assert ":" in key

    def test_exclude_filters_nics(self):
        from core.psutil_bindings import net_io_counters_per_nic
        import psutil
        # Get all NIC names
        all_nics = list(psutil.net_io_counters(pernic=True).keys())
        if len(all_nics) < 2:
            pytest.skip("Need at least 2 NICs to test filtering")
        # Exclude the first NIC
        target = all_nics[0]
        result = net_io_counters_per_nic(exclude=[f"^{re.escape(target)}$"])
        # No keys should start with the excluded NIC
        for key in result.keys():
            assert not key.startswith(f"{target}:")

    def test_include_filters_nics(self):
        from core.psutil_bindings import net_io_counters_per_nic
        import psutil
        all_nics = list(psutil.net_io_counters(pernic=True).keys())
        if len(all_nics) < 2:
            pytest.skip("Need at least 2 NICs to test filtering")
        # Include only the first NIC
        target = all_nics[0]
        result = net_io_counters_per_nic(include=[f"^{re.escape(target)}$"])
        # All keys should start with the included NIC
        for key in result.keys():
            assert key.startswith(f"{target}:")


# --- Network IO rate calculation with RateCalculator ---

class TestNetIORateCalculation:
    def test_rate_calculator_with_net_io_counters(self):
        from core.rate import RateCalculator
        rc = RateCalculator()
        counters1 = {"bytes_sent": 100.0, "bytes_recv": 200.0, "packets_sent": 10.0, "packets_recv": 20.0}
        # First call returns zeros
        result = rc.update(counters1)
        assert all(v == 0.0 for v in result.values())

        # Second call should produce rates > 0 (time has elapsed)
        import time
        time.sleep(0.05)
        counters2 = {"bytes_sent": 200.0, "bytes_recv": 400.0, "packets_sent": 20.0, "packets_recv": 40.0}
        result = rc.update(counters2)
        assert result["bytes_sent"] > 0
        assert result["bytes_recv"] > 0
        assert result["packets_sent"] > 0
        assert result["packets_recv"] > 0
