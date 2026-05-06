"""Select entity — interactive entity with command template, state map, and optional feedback.

Select extends InteractiveEntity. It creates an HA select entity, executes a
command template with mapped values on selection, and optionally uses a
CommandFetcher for state feedback with inverse state map.
"""

import logging

from core.entities.fetcher import CommandFetcher
from core.entities.interactive import InteractiveEntity
from core.subprocess import CommandFailed, CommandTimeout, run_command

logger = logging.getLogger(__name__)


class Select(InteractiveEntity):
    """Select entity with command template, state map, and optional feedback sensor.

    - On MQTT selection: maps via state_map, formats command template, executes
    - If sensor config is present: uses CommandFetcher for state feedback
    - Feedback values are inverse-mapped through state_map before updating state
    - If no feedback: uses optimistic state (updates immediately after command)
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        self._state_map: dict[str, str] = config.state_map or {}
        self._inverse_map: dict[str, str] = {v: k for k, v in self._state_map.items()}
        self._last_option: str | None = None
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)

    def _create_ha_entity(self):
        """Create HA select entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Select as HASelect,
            SelectInfo as HASelectInfo,
        )

        options = list(self._state_map.keys()) if self._state_map else []
        entity_info = HASelectInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
            options=options,
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HASelect(settings, self._on_command)

    def _setup_feedback(self) -> None:
        """Create a CommandFetcher from config.sensor if present."""
        if self._config.sensor:
            self._feedback_fetcher = CommandFetcher(
                self._config.sensor,
                callback=self._on_feedback,
                parser_configs=self._config.sensor.parse,
                availability_callback=self._on_availability,
            )

    def _on_availability(self, available: bool) -> None:
        """Publish availability state to HA entity."""
        self._ha_entity.set_availability(available)

    def _on_command(self, client, user_data, message) -> None:
        """MQTT callback when a selection is received — dispatch to async queue."""
        payload = message.payload.decode()
        self._dispatch_command(payload)

    def _on_feedback(self, value) -> None:
        """Apply inverse state map to feedback value before updating state."""
        display_value = self._inverse_map.get(str(value), str(value))
        self._update_state(display_value)

    async def _execute_action(self, payload: str) -> None:
        """Map via state_map, format command template, execute asynchronously."""
        mapped = self._state_map.get(payload, payload)
        command = self._config.command_template.format(mapped)
        shell = self._config.shell
        timeout = getattr(self._config, "command_timeout", 30.0)

        try:
            await run_command(command, shell, timeout)
        except CommandTimeout:
            logger.warning(
                "Select '%s' command timed out after %ss: %s",
                self._config.name,
                timeout,
                command,
            )
            return
        except CommandFailed as e:
            logger.error(
                "Select '%s' command failed: %s",
                self._config.name,
                e,
            )
            return

        # Optimistic state update if no feedback fetcher
        if not self._feedback_fetcher:
            self._update_state(payload)

    def _update_state(self, value) -> None:
        """Update HA select state with the current option."""
        self._last_option = str(value)
        self._ha_entity.select_option(self._last_option)

    def _republish_state(self) -> None:
        """Re-publish last known selected option."""
        if self._last_option is not None:
            try:
                self._ha_entity.select_option(self._last_option)
            except Exception as e:
                logger.warning("Failed to republish state for select '%s': %s", self._config.name, e)
