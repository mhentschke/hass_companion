"""Switch entity — interactive entity with ON/OFF commands and optional state feedback.

Switch extends InteractiveEntity. It creates an HA switch entity, executes
command_on/command_off on MQTT commands, and optionally uses a CommandFetcher
for state feedback from a binary sensor.
"""

import logging

from core.entities.fetcher import CommandFetcher
from core.entities.interactive import InteractiveEntity
from core.subprocess import CommandFailed, CommandTimeout, run_command

logger = logging.getLogger(__name__)


class Switch(InteractiveEntity):
    """Switch entity with ON/OFF commands and optional feedback sensor.

    - On MQTT ON command: executes command_on
    - On MQTT OFF command: executes command_off
    - If binary_sensor config is present: uses CommandFetcher for state feedback
    - If no feedback: uses optimistic state (updates immediately after command)
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        self._last_state = None
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)

    def _create_ha_entity(self):
        """Create HA switch entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Switch as HASwitch,
        )
        from ha_mqtt_discoverable.sensors import (
            SwitchInfo as HASwitchInfo,
        )

        entity_info = HASwitchInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HASwitch(settings, self._on_command)

    def _setup_feedback(self) -> None:
        """Create a CommandFetcher from config.binary_sensor if present."""
        if self._config.binary_sensor:
            self._feedback_fetcher = CommandFetcher(
                self._config.binary_sensor,
                callback=self._on_feedback,
                parser_configs=self._config.binary_sensor.parse,
                availability_callback=self._on_availability,
            )

    def _on_availability(self, available: bool) -> None:
        """Publish availability state to HA entity."""
        self._ha_entity.set_availability(available)

    def _on_command(self, client, user_data, message) -> None:
        """MQTT callback when switch command is received — dispatch to async queue."""
        payload = message.payload.decode()
        if payload == "ON":
            self._dispatch_command("on")
        elif payload == "OFF":
            self._dispatch_command("off")

    async def _execute_action(self, payload: str) -> None:
        """Execute the on or off command asynchronously."""
        command = self._config.command_on if payload == "on" else self._config.command_off
        shell = self._config.shell
        timeout = self._config.command_timeout

        try:
            await run_command(command, shell, timeout)
        except CommandTimeout:
            logger.warning(
                "Switch '%s' command timed out after %ss: %s",
                self._config.name,
                timeout,
                command,
            )
            return
        except CommandFailed as e:
            logger.error(
                "Switch '%s' command failed: %s",
                self._config.name,
                e,
            )
            return

        # Optimistic state update if no feedback fetcher
        if not self._feedback_fetcher:
            self._update_state(payload == "on")

    def _update_state(self, value) -> None:
        """Update HA switch state."""
        self._last_state = value
        if value:
            self._ha_entity.on()
        else:
            self._ha_entity.off()

    def _republish_state(self) -> None:
        """Re-publish last known switch state."""
        if self._last_state is not None:
            try:
                self._update_state(self._last_state)
            except Exception as e:
                logger.warning("Failed to republish state for switch '%s': %s", self._config.name, e)
