"""Button entity — executes a command on press, no polling or state feedback.

Button extends Entity directly. It subscribes to MQTT press commands
and executes a shell command when triggered.
"""

import logging
import subprocess

from core.entities.base import Entity

logger = logging.getLogger(__name__)

DEFAULT_BUTTON_TIMEOUT = 30.0


class Button(Entity):
    """Button entity that executes a command on press.

    No polling, no fetcher, no state feedback. Simply runs a shell command
    when the HA button is pressed.
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)

    def _create_ha_entity(self):
        """Create HA button entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Button as HAButton,
            ButtonInfo as HAButtonInfo,
        )

        entity_info = HAButtonInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info)
        return HAButton(settings, self._on_press)

    def _on_press(self, client, user_data, message) -> None:
        """MQTT callback when button is pressed — execute the configured command."""
        command = self._config.command
        shell = self._config.shell
        timeout = getattr(self._config, "command_timeout", DEFAULT_BUTTON_TIMEOUT)

        try:
            subprocess.run(
                [shell, "--noprofile", "--norc", "-c", command],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Button '%s' command timed out after %ss: %s",
                self._config.name,
                timeout,
                command,
            )
        except Exception as e:
            logger.error(
                "Button '%s' command failed: %s",
                self._config.name,
                e,
            )
