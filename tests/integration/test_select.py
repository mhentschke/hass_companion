"""Integration tests for Select entity with async command execution and mocked HA entity."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.config import SelectConfig, SensorConfig
from core.entities.select import Select


def _make_select(
    command_template="set-mode {}",
    state_map=None,
    sensor=None,
    _ha_entity=None,
):
    """Helper to create a Select with a mock HA entity."""
    sensor_config = None
    if sensor:
        sensor_config = SensorConfig(**sensor)

    config = SelectConfig(
        name="Test Select",
        id="test_select",
        command_template=command_template,
        state_map=state_map or {"Low": "low", "Medium": "med", "High": "high"},
        sensor=sensor_config,
    )
    mock_ha = _ha_entity or Mock()
    select = Select(config, mqtt_settings=None, device=None, _ha_entity=mock_ha)
    return select, mock_ha


@pytest.mark.asyncio
@patch("core.entities.select.run_command", new_callable=AsyncMock)
async def test_select_executes_command_with_mapped_value(mock_run_command):
    """Verify select formats command template with state_map mapped value."""
    mock_run_command.return_value = ""
    select, mock_ha = _make_select()
    try:
        await select._execute_action("Low")
        mock_run_command.assert_called_once_with("set-mode low", "bash", 30.0)
    finally:
        select.stop()


@pytest.mark.asyncio
@patch("core.entities.select.run_command", new_callable=AsyncMock)
async def test_select_optimistic_state_update(mock_run_command):
    """Verify select updates HA state optimistically when no feedback sensor."""
    mock_run_command.return_value = ""
    select, mock_ha = _make_select()
    try:
        await select._execute_action("High")
        mock_ha.select_option.assert_called_once_with("High")
    finally:
        select.stop()


@pytest.mark.asyncio
@patch("core.entities.fetcher.run_command", new_callable=AsyncMock)
async def test_select_feedback_sensor_inverse_mapping(mock_run_command):
    """Verify feedback sensor applies inverse state map before updating state."""
    mock_run_command.return_value = "med"
    select, mock_ha = _make_select(
        sensor={
            "command": "get-mode",
            "polling_interval": 0.1,
            "parse": [],
        },
    )
    try:
        task = asyncio.create_task(select.run())
        await asyncio.sleep(0.3)
        # Feedback value "med" should be inverse-mapped to "Medium"
        mock_ha.select_option.assert_called_with("Medium")
    finally:
        select.stop()
        await task


@pytest.mark.asyncio
@patch("core.entities.fetcher.run_command", new_callable=AsyncMock)
@patch("core.entities.select.run_command", new_callable=AsyncMock)
async def test_select_no_optimistic_update_with_feedback(mock_select_run, mock_fetcher_run):
    """Verify select does NOT update state optimistically when feedback sensor exists."""
    mock_fetcher_run.return_value = "low"
    mock_select_run.return_value = ""
    select, mock_ha = _make_select(
        sensor={
            "command": "get-mode",
            "polling_interval": 10.0,
            "parse": [],
        },
    )
    try:
        mock_ha.reset_mock()
        await select._execute_action("High")
        # With feedback sensor present, should NOT call select_option
        mock_ha.select_option.assert_not_called()
    finally:
        select.stop()
