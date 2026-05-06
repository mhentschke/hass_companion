"""BinarySensor entities — sensors that enforce boolean output.

BinarySensor extends Sensor with bool coercion before publishing.
CommandBinarySensor uses a CommandFetcher for subprocess-based value retrieval.
"""

import logging

from core.config import DEFAULT_BINARY_SENSOR_INTERVAL
from core.entities.fetcher import CommandFetcher, StateFetcher
from core.entities.sensor import Sensor

logger = logging.getLogger(__name__)


class BinarySensor(Sensor):
    """Sensor that enforces boolean output before publishing state.

    Overrides _on_value() to coerce any parsed value to bool using Python
    truthiness rules, then calls update_state() on the HA binary sensor entity.
    """

    def _on_value(self, value) -> None:
        """Coerce value to bool and publish to HA entity."""
        bool_value = bool(value)
        self._last_value = bool_value
        if bool_value:
            self._ha_entity.on()
        else:
            self._ha_entity.off()

    def _republish_state(self) -> None:
        """Re-publish last known binary sensor state."""
        if self._last_value is not None:
            try:
                if self._last_value:
                    self._ha_entity.on()
                else:
                    self._ha_entity.off()
            except Exception as e:
                logger.warning("Failed to republish state for binary sensor: %s", e)

    def _create_fetcher(self) -> StateFetcher:
        """Subclasses provide the appropriate fetcher type."""
        raise NotImplementedError

    def _create_ha_entity(self):
        """Create HA binary sensor entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            BinarySensor as HABinarySensor,
            BinarySensorInfo as HABinarySensorInfo,
        )

        entity_info = HABinarySensorInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
            device_class=getattr(self._config, "device_class", None),
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HABinarySensor(settings)


class CommandBinarySensor(BinarySensor):
    """BinarySensor that gets its value from a shell command."""

    def _create_fetcher(self) -> StateFetcher:
        return CommandFetcher(
            self._config,
            callback=self._on_value,
            parser_configs=self._config.parse,
            availability_callback=self._on_availability,
        )

    def _on_availability(self, available: bool) -> None:
        """Publish availability state to HA entity."""
        self._ha_entity.set_availability(available)

    def _create_ha_entity(self):
        """Create HA binary sensor entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            BinarySensor as HABinarySensor,
            BinarySensorInfo as HABinarySensorInfo,
        )

        entity_info = HABinarySensorInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
            device_class=getattr(self._config, "device_class", None),
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HABinarySensor(settings)
