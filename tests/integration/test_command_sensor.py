"""Integration tests for CommandSensor with mocked HA entity."""

import asyncio
from unittest.mock import Mock

import pytest

from core.config import SensorConfig
from core.entities.sensor import CommandSensor


def _make_sensor(command="echo 42", parse=None, timeout=30, interval=0.1, _ha_entity=None):
    """Helper to create a CommandSensor with a mock HA entity."""
    if parse is None:
        parse = [{"type": "int"}]
    config = SensorConfig(
        name="Test Sensor",
        id="test_sensor",
        command=command,
        polling_interval=interval,
        command_timeout=timeout,
        parse=parse,
    )
    mock_ha = _ha_entity or Mock()
    sensor = CommandSensor(config, mqtt_settings=None, device=None, _ha_entity=mock_ha)
    return sensor, mock_ha


@pytest.mark.asyncio
async def test_command_sensor_publishes_parsed_state():
    """Verify set_state is called with the parsed integer value."""
    sensor, mock_ha = _make_sensor(command="echo 42", parse=[{"type": "int"}])
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.3)
        mock_ha.set_state.assert_called_with(42)
    finally:
        sensor.stop()
        await task


@pytest.mark.asyncio
async def test_command_sensor_timeout_handling():
    """Verify timeout is handled gracefully without crashing."""
    sensor, mock_ha = _make_sensor(command="sleep 10", timeout=0.1, interval=0.2)
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.5)
        # set_state should NOT have been called (command timed out)
        mock_ha.set_state.assert_not_called()
        # Fetcher should have recorded failures
        assert sensor._fetcher._failure_count >= 1
    finally:
        sensor.stop()
        await task


@pytest.mark.asyncio
async def test_command_sensor_exception_handling():
    """Verify general exceptions are handled gracefully."""
    sensor, mock_ha = _make_sensor(
        command="echo hello",
        parse=[{"type": "int"}],  # int("hello") will raise ValueError
        interval=0.1,
    )
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.4)
        # set_state should NOT have been called (parser raised)
        mock_ha.set_state.assert_not_called()
        assert sensor._fetcher._failure_count >= 1
    finally:
        sensor.stop()
        await task
