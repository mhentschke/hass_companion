"""Sensor entities — read-only entities that poll a value and publish state.

Sensor composes a StateFetcher whose callback publishes to the HA entity.
CommandSensor uses a CommandFetcher for subprocess-based value retrieval.
"""

import logging

from core.config import DEFAULT_SENSOR_INTERVAL
from core.entities.base import BaseEntity
from core.entities.fetcher import CommandFetcher, StateFetcher

logger = logging.getLogger(__name__)


class Sensor(BaseEntity):
    """Read-only entity that polls a value source and publishes state.

    Composes a StateFetcher. Subclasses provide the fetcher type via _create_fetcher().
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)
        self._fetcher = self._create_fetcher()
        self._fetcher.start()

    def _create_fetcher(self) -> StateFetcher:
        """Subclasses provide the appropriate fetcher type."""
        raise NotImplementedError

    def _on_value(self, value) -> None:
        """Callback from fetcher — publish to HA entity."""
        self._ha_entity.set_state(value)

    def stop(self) -> None:
        """Stop the polling fetcher."""
        self._fetcher.stop()


class CommandSensor(Sensor):
    """Sensor that gets its value from a shell command."""

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
        """Create HA sensor entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Sensor as HASensor,
            SensorInfo as HASensorInfo,
        )

        entity_info = HASensorInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
            unit_of_measurement=getattr(self._config, "unit_of_measurement", None),
            device_class=getattr(self._config, "device_class", None),
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HASensor(settings)
