"""Integration tests for DNSSensor — async DNS lookup with mocked subprocess."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.config import DNSHostConfig
from core.network_sensors import DNSSensor


DIG_SUCCESS_OUTPUT = (
    "; <<>> DiG 9.18.18 <<>> google.com\n"
    ";; global options: +cmd\n"
    ";; Got answer:\n"
    ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 12345\n"
    ";; flags: qr rd ra; QUERY: 1, ANSWER: 1, AUTHORITY: 0, ADDITIONAL: 1\n"
    "\n"
    ";; QUESTION SECTION:\n"
    ";google.com.\t\t\tIN\tA\n"
    "\n"
    ";; ANSWER SECTION:\n"
    "google.com.\t\t300\tIN\tA\t142.250.80.46\n"
    "\n"
    ";; Query time: 23 msec\n"
    ";; SERVER: 192.168.1.1#53(192.168.1.1) (UDP)\n"
    ";; WHEN: Wed May 06 12:00:00 UTC 2026\n"
    ";; MSG SIZE  rcvd: 55\n"
    "\n"
)

DIG_FAILURE_OUTPUT = """\
; <<>> DiG 9.18.18 <<>> nonexistent.invalid
;; global options: +cmd
;; connection timed out; no servers could be reached
"""


def _make_mock_process(stdout_text: str, returncode: int = 0):
    """Create a mock async subprocess that returns given stdout."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(
        return_value=(stdout_text.encode(), b"")
    )
    mock_proc.returncode = returncode
    return mock_proc


class TestDNSSensor:
    """Tests for DNSSensor with mocked asyncio.create_subprocess_exec."""

    @pytest.mark.asyncio
    async def test_successful_lookup_updates_sensor(self):
        """resolution_time sensor receives correct value on success."""
        mock_resolution = Mock()
        ha_entities = {"resolution_time": mock_resolution}

        config = DNSHostConfig(host="google.com", polling_interval=0.1)
        sensor = DNSSensor(None, None, config=config, _ha_entities=ha_entities)

        mock_proc = _make_mock_process(DIG_SUCCESS_OUTPUT)

        with patch("core.network_sensors.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(sensor.run())
            await asyncio.sleep(0.25)
            sensor.stop()
            await task

        mock_resolution.set_state.assert_called_with(23.0)

    @pytest.mark.asyncio
    async def test_failure_marks_unavailable_after_threshold(self):
        """Sensor becomes unavailable after 3 consecutive failures."""
        mock_resolution = Mock()
        mock_resolution.set_availability = Mock()
        ha_entities = {"resolution_time": mock_resolution}

        config = DNSHostConfig(host="nonexistent.invalid", polling_interval=0.05)
        sensor = DNSSensor(None, None, config=config, _ha_entities=ha_entities)

        mock_proc = _make_mock_process(DIG_FAILURE_OUTPUT)

        with patch("core.network_sensors.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(sensor.run())
            await asyncio.sleep(0.35)
            sensor.stop()
            await task

        assert sensor._available is False
        mock_resolution.set_availability.assert_called_with(False)

    @pytest.mark.asyncio
    async def test_recovery_after_failure(self):
        """Sensor becomes available again after recovery from failures."""
        mock_resolution = Mock()
        mock_resolution.set_availability = Mock()
        ha_entities = {"resolution_time": mock_resolution}

        config = DNSHostConfig(host="google.com", polling_interval=0.05)
        sensor = DNSSensor(None, None, config=config, _ha_entities=ha_entities)

        call_count = {"n": 0}
        failure_proc = _make_mock_process(DIG_FAILURE_OUTPUT)
        success_proc = _make_mock_process(DIG_SUCCESS_OUTPUT)

        async def mock_subprocess(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 3:
                return failure_proc
            return success_proc

        with patch("core.network_sensors.asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            task = asyncio.create_task(sensor.run())
            await asyncio.sleep(0.5)
            sensor.stop()
            await task

        assert sensor._available is True
        mock_resolution.set_availability.assert_called_with(True)
