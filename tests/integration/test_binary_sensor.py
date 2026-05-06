"""Integration tests for CommandBinarySensor with mocked HA entity."""

import asyncio

import pytest
from unittest.mock import Mock

from core.config import BinarySensorConfig
from core.entities.binary_sensor import CommandBinarySensor


def _make_binary_sensor(command="echo 1", parse=None, interval=0.1, _ha_entity=None):
    """Helper to create a CommandBinarySensor with a mock HA entity."""
    if parse is None:
        parse = [{"type": "bool"}]
    config = BinarySensorConfig(
        name="Test Binary Sensor",
        id="test_binary_sensor",
        command=command,
        polling_interval=interval,
        command_timeout=30.0,
        parse=parse,
    )
    mock_ha = _ha_entity or Mock()
    sensor = CommandBinarySensor(config, mqtt_settings=None, device=None, _ha_entity=mock_ha)
    return sensor, mock_ha


@pytest.mark.asyncio
async def test_binary_sensor_coerces_truthy_to_true():
    """Verify truthy command output is coerced to True."""
    sensor, mock_ha = _make_binary_sensor(command="echo 1", parse=[{"type": "int"}])
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.3)
        mock_ha.update_state.assert_called_with(True)
    finally:
        sensor.stop()
        await task


@pytest.mark.asyncio
async def test_binary_sensor_coerces_falsy_to_false():
    """Verify falsy command output is coerced to False."""
    sensor, mock_ha = _make_binary_sensor(command="echo 0", parse=[{"type": "int"}])
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.3)
        mock_ha.update_state.assert_called_with(False)
    finally:
        sensor.stop()
        await task


@pytest.mark.asyncio
async def test_binary_sensor_update_state_called_with_boolean():
    """Verify update_state is always called with a boolean type."""
    sensor, mock_ha = _make_binary_sensor(command="echo hello", parse=[{"type": "string"}])
    task = asyncio.create_task(sensor.run())
    try:
        await asyncio.sleep(0.3)
        # Non-empty string "hello" is truthy
        mock_ha.update_state.assert_called_with(True)
        # Verify the argument is actually a bool, not just truthy
        call_arg = mock_ha.update_state.call_args[0][0]
        assert isinstance(call_arg, bool)
    finally:
        sensor.stop()
        await task
