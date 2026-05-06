"""Integration tests for Button entity with mocked subprocess."""

import subprocess
from unittest.mock import Mock, patch

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


@patch("core.entities.button.subprocess.run")
def test_button_executes_command_on_press(mock_run):
    """Verify pressing the button executes the configured command."""
    button, _ = _make_button(command="echo pressed")
    button._on_press(None, None, None)
    mock_run.assert_called_once_with(
        ["bash", "--noprofile", "--norc", "-c", "echo pressed"],
        capture_output=True,
        text=True,
        timeout=30.0,
    )


@patch("core.entities.button.subprocess.run")
def test_button_handles_timeout(mock_run):
    """Verify button handles subprocess timeout gracefully."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="sleep 999", timeout=30.0)
    button, _ = _make_button(command="sleep 999")
    # Should not raise
    button._on_press(None, None, None)


@patch("core.entities.button.subprocess.run")
def test_button_handles_exception(mock_run):
    """Verify button handles general subprocess exceptions gracefully."""
    mock_run.side_effect = OSError("Command not found")
    button, _ = _make_button(command="nonexistent_cmd")
    # Should not raise
    button._on_press(None, None, None)
