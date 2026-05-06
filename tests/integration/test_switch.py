"""Integration tests for Switch entity with async command execution and mocked HA entity."""

import asyncio

import pytest
from unittest.mock import AsyncMock, Mock, patch

from core.config import BinarySensorConfig, SwitchConfig
from core.entities.switch import Switch


def _make_switch(
    command_on="echo ON",
    command_off="echo OFF",
    binary_sensor=None,
    _ha_entity=None,
):
    """Helper to create a Switch with a mock HA entity."""
    bs_config = None
    if binary_sensor:
        bs_config = BinarySensorConfig(**binary_sensor)

    config = SwitchConfig(
        name="Test Switch",
        id="test_switch",
        command_on=command_on,
        command_off=command_off,
        binary_sensor=bs_config,
    )
    mock_ha = _ha_entity or Mock()
    switch = Switch(config, mqtt_settings=None, device=None, _ha_entity=mock_ha)
    return switch, mock_ha


@pytest.mark.asyncio
@patch("core.entities.switch.run_command", new_callable=AsyncMock)
async def test_switch_executes_on_command(mock_run_command):
    """Verify switch executes command_on when ON action is triggered."""
    mock_run_command.return_value = ""
    switch, mock_ha = _make_switch(command_on="echo ON")
    try:
        await switch._execute_action("on")
        mock_run_command.assert_called_once_with("echo ON", "bash", 30.0)
    finally:
        switch.stop()


@pytest.mark.asyncio
@patch("core.entities.switch.run_command", new_callable=AsyncMock)
async def test_switch_executes_off_command(mock_run_command):
    """Verify switch executes command_off when OFF action is triggered."""
    mock_run_command.return_value = ""
    switch, mock_ha = _make_switch(command_off="echo OFF")
    try:
        await switch._execute_action("off")
        mock_run_command.assert_called_once_with("echo OFF", "bash", 30.0)
    finally:
        switch.stop()


@pytest.mark.asyncio
@patch("core.entities.switch.run_command", new_callable=AsyncMock)
async def test_switch_optimistic_state_on(mock_run_command):
    """Verify switch updates HA state optimistically to ON when no feedback sensor."""
    mock_run_command.return_value = ""
    switch, mock_ha = _make_switch()
    try:
        await switch._execute_action("on")
        mock_ha.on.assert_called_once()
    finally:
        switch.stop()


@pytest.mark.asyncio
@patch("core.entities.switch.run_command", new_callable=AsyncMock)
async def test_switch_optimistic_state_off(mock_run_command):
    """Verify switch updates HA state optimistically to OFF when no feedback sensor."""
    mock_run_command.return_value = ""
    switch, mock_ha = _make_switch()
    try:
        await switch._execute_action("off")
        mock_ha.off.assert_called_once()
    finally:
        switch.stop()


@pytest.mark.asyncio
@patch("core.entities.fetcher.run_command", new_callable=AsyncMock)
async def test_switch_feedback_sensor_routes_state(mock_run_command):
    """Verify feedback sensor updates switch state instead of optimistic update."""
    mock_run_command.return_value = "1"
    switch, mock_ha = _make_switch(
        binary_sensor={
            "command": "echo 1",
            "polling_interval": 0.1,
            "parse": [{"type": "bool"}],
        },
    )
    try:
        task = asyncio.create_task(switch.run())
        # Wait for feedback fetcher to poll
        await asyncio.sleep(0.3)
        # Feedback sensor should have called _update_state via _on_feedback
        mock_ha.on.assert_called()
    finally:
        switch.stop()
        await task


@pytest.mark.asyncio
@patch("core.entities.fetcher.run_command", new_callable=AsyncMock)
@patch("core.entities.switch.run_command", new_callable=AsyncMock)
async def test_switch_no_optimistic_update_with_feedback(mock_switch_run, mock_fetcher_run):
    """Verify switch does NOT update state optimistically when feedback sensor exists."""
    mock_fetcher_run.return_value = "0"
    mock_switch_run.return_value = ""
    switch, mock_ha = _make_switch(
        binary_sensor={
            "command": "echo 0",
            "polling_interval": 10.0,
            "parse": [{"type": "bool"}],
        },
    )
    try:
        # Reset mock to clear any calls from feedback fetcher startup
        mock_ha.reset_mock()
        await switch._execute_action("on")
        # With feedback sensor present, _execute_action should NOT call on()/off()
        mock_ha.on.assert_not_called()
        mock_ha.off.assert_not_called()
    finally:
        switch.stop()
