"""Integration tests for Button entity with async command execution."""

import asyncio

import pytest
from unittest.mock import AsyncMock, Mock, patch

from core.config import ButtonConfig
from core.entities.button import Button


def _make_button(command="echo hello", shell="bash", _ha_entity=None):
    """Helper to create a Button with a mock HA entity."""
    config = ButtonConfig(
        name="Test Button",
        id="test_button",
        command=command,
        shell=shell,
    )
    mock_ha = _ha_entity or Mock()
    button = Button(config, mqtt_settings=None, device=None, _ha_entity=mock_ha)
    return button, mock_ha


@pytest.mark.asyncio
@patch("core.entities.button.run_command", new_callable=AsyncMock)
async def test_button_executes_command_on_press(mock_run_command):
    """Verify pressing the button executes the configured command."""
    mock_run_command.return_value = ""
    button, _ = _make_button(command="echo pressed")

    # Dispatch press to the queue
    button._command_queue.put_nowait("press")

    # Run the button briefly to process the queue item
    task = asyncio.create_task(button.run())
    await asyncio.sleep(0.05)
    button._exit.set()
    await task

    mock_run_command.assert_called_once_with("echo pressed", "bash", 30.0)


@pytest.mark.asyncio
@patch("core.entities.button.run_command", new_callable=AsyncMock)
async def test_button_handles_timeout(mock_run_command):
    """Verify button handles command timeout gracefully."""
    from core.subprocess import CommandTimeout
    mock_run_command.side_effect = CommandTimeout("timed out")
    button, _ = _make_button(command="sleep 999")

    button._command_queue.put_nowait("press")
    task = asyncio.create_task(button.run())
    await asyncio.sleep(0.05)
    button._exit.set()
    await task

    # Should not raise — timeout is handled gracefully


@pytest.mark.asyncio
@patch("core.entities.button.run_command", new_callable=AsyncMock)
async def test_button_handles_exception(mock_run_command):
    """Verify button handles command failure gracefully."""
    from core.subprocess import CommandFailed
    mock_run_command.side_effect = CommandFailed("Command not found")
    button, _ = _make_button(command="nonexistent_cmd")

    button._command_queue.put_nowait("press")
    task = asyncio.create_task(button.run())
    await asyncio.sleep(0.05)
    button._exit.set()
    await task

    # Should not raise — failure is handled gracefully
