"""Sensor entities — read-only entities that poll a value and publish state.

Sensor composes a StateFetcher whose callback publishes to the HA entity.
CommandSensor uses a CommandFetcher for subprocess-based value retrieval.
"""

import logging

from core.config import DEFAULT_SENSOR_INTERVAL
from core.entities.base import Entity
from core.entities.fetcher import CommandFetcher, StateFetcher, SystemFetcher

logger = logging.getLogger(__name__)


class Sensor(Entity):
    """Read-only entity that polls a value source and publishes state.

    Composes a StateFetcher. Subclasses provide the fetcher type via _create_fetcher().
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)
        self._fetcher = self._create_fetcher()
        self._last_value = None

    def _create_fetcher(self) -> StateFetcher:
        """Subclasses provide the appropriate fetcher type."""
        raise NotImplementedError

    def start(self) -> None:
        """Start the fetcher in a background thread (backward compat bridge)."""
        self._fetcher.start()

    async def run(self) -> None:
        """Run the fetcher's async poll loop."""
        await self._fetcher.run()

    def _on_value(self, value) -> None:
        """Callback from fetcher — publish to HA entity."""
        self._last_value = value
        self._ha_entity.set_state(value)

    def _republish_state(self) -> None:
        """Re-publish last known sensor state."""
        if self._last_value is not None:
            try:
                self._ha_entity.set_state(self._last_value)
            except Exception as e:
                logger.warning("Failed to republish state for sensor: %s", e)

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


class SystemSensor(Sensor):
    """Sensor backed by a Python callable (e.g., psutil.cpu_percent).

    For scalar-returning functions. Creates a single HA sensor entity.
    Used when a system metric produces a single value (not a dict/list).
    """

    def __init__(
        self,
        mqtt_settings,
        device,
        *,
        fn,
        name: str,
        unique_id: str,
        interval: float,
        icon: str | None = None,
        unit_of_measurement: str | None = None,
        _ha_entity=None,
    ):
        self._fn = fn
        self._system_name = name
        self._system_id = unique_id
        self._system_interval = interval
        self._system_icon = icon
        self._system_unit = unit_of_measurement
        # Pass a minimal config-like object — Sensor.__init__ expects config
        super().__init__(
            config=None,
            mqtt_settings=mqtt_settings,
            device=device,
            _ha_entity=_ha_entity,
        )

    def _create_fetcher(self) -> StateFetcher:
        return SystemFetcher(
            callback=self._on_value,
            fn=self._fn,
            interval=self._system_interval,
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
            name=self._system_name,
            unique_id=self._system_id,
            device=self._device,
            icon=self._system_icon,
            unit_of_measurement=self._system_unit,
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info)
        return HASensor(settings)
