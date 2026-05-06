"""Integration tests for PingSensor — async ping with mocked subprocess."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.config import PingHostConfig
from core.network_sensors import PingSensor


PING_SUCCESS_OUTPUT = """\
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms

--- 8.8.8.8 ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 12.3/12.3/12.3/0.0 ms
"""

PING_TIMEOUT_OUTPUT = """\
PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.

--- 8.8.8.8 ping statistics ---
1 packets transmitted, 0 received, 100% packet loss, time 0ms
"""


def _make_mock_process(stdout_text: str, returncode: int = 0):
    """Create a mock async subprocess that returns given stdout."""
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(
        return_value=(stdout_text.encode(), b"")
    )
    mock_proc.returncode = returncode
    return mock_proc


class TestPingSensor:
    """Tests for PingSensor with mocked asyncio.create_subprocess_exec."""

    @pytest.mark.asyncio
    async def test_successful_ping_updates_sensors(self):
        """RTT and packet_loss sensors receive correct values on success."""
        mock_rtt = Mock()
        mock_loss = Mock()
        ha_entities = {"rtt": mock_rtt, "packet_loss": mock_loss}

        config = PingHostConfig(host="8.8.8.8", polling_interval=0.1)
        sensor = PingSensor(None, None, config=config, _ha_entities=ha_entities)

        mock_proc = _make_mock_process(PING_SUCCESS_OUTPUT)

        with patch("core.network_sensors.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(sensor.run())
            await asyncio.sleep(0.25)
            sensor.stop()
            await task

        mock_rtt.set_state.assert_called_with(12.3)
        mock_loss.set_state.assert_called_with(0.0)

    @pytest.mark.asyncio
    async def test_timeout_marks_unavailable_after_threshold(self):
        """Sensor becomes unavailable after 3 consecutive failures."""
        mock_rtt = Mock()
        mock_rtt.set_availability = Mock()
        mock_loss = Mock()
        mock_loss.set_availability = Mock()
        ha_entities = {"rtt": mock_rtt, "packet_loss": mock_loss}

        config = PingHostConfig(host="8.8.8.8", polling_interval=0.05, timeout=1.0)
        sensor = PingSensor(None, None, config=config, _ha_entities=ha_entities)

        mock_proc = _make_mock_process(PING_TIMEOUT_OUTPUT)

        with patch("core.network_sensors.asyncio.create_subprocess_exec", return_value=mock_proc):
            task = asyncio.create_task(sensor.run())
            # Wait for at least 3 poll cycles
            await asyncio.sleep(0.35)
            sensor.stop()
            await task

        assert sensor._available is False
        mock_rtt.set_availability.assert_called_with(False)
        mock_loss.set_availability.assert_called_with(False)

    @pytest.mark.asyncio
    async def test_recovery_after_timeout(self):
        """Sensor becomes available again after recovery from failures."""
        mock_rtt = Mock()
        mock_rtt.set_availability = Mock()
        mock_loss = Mock()
        mock_loss.set_availability = Mock()
        ha_entities = {"rtt": mock_rtt, "packet_loss": mock_loss}

        config = PingHostConfig(host="8.8.8.8", polling_interval=0.05, timeout=1.0)
        sensor = PingSensor(None, None, config=config, _ha_entities=ha_entities)

        call_count = {"n": 0}
        timeout_proc = _make_mock_process(PING_TIMEOUT_OUTPUT)
        success_proc = _make_mock_process(PING_SUCCESS_OUTPUT)

        async def mock_subprocess(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] <= 3:
                return timeout_proc
            return success_proc

        with patch("core.network_sensors.asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            task = asyncio.create_task(sensor.run())
            # Wait for 3 failures + 1 success
            await asyncio.sleep(0.4)
            sensor.stop()
            await task

        # Should have recovered
        assert sensor._available is True
        mock_rtt.set_availability.assert_called_with(True)
