"""ConfigStatusSensor — built-in HA sensor reporting configuration reload status.

Created unconditionally at startup. Reports whether the last config reload
succeeded or failed, with attributes for timestamps and entity counts.
"""

import json
import logging
from datetime import datetime, timezone

from core.entities.base import BaseEntity

logger = logging.getLogger(__name__)


class ConfigStatusSensor(BaseEntity):
    """Built-in sensor that reports config reload status to Home Assistant.

    State: 'valid' | 'error' | 'restart_required'
    Attributes: last_reload, last_error, last_error_time,
                entities_added, entities_removed, entities_updated,
                restart_reasons
    """

    def __init__(self, mqtt_settings, device, *, device_id: str, _ha_entity=None):
        super().__init__(mqtt_settings, device)
        self._device_id = device_id
        self._unique_id = f"{device_id}_config_status"
        self._state = "valid"
        self._attributes = {
            "last_reload": None,
            "last_error": None,
            "last_error_time": None,
            "entities_added": 0,
            "entities_removed": 0,
            "entities_updated": 0,
            "restart_reasons": [],
        }
        self._ha_entity = _ha_entity or self._create_ha_entity()
        # Publish initial availability and state
        self._ha_entity.set_availability(True)
        self._publish_state()

    def _create_ha_entity(self):
        """Create the HA sensor entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import SensorInfo as HASensorInfo

        from core.ha_entities import Sensor as HASensor

        entity_info = HASensorInfo(
            name="Config Status",
            unique_id=self._unique_id,
            device=self._device,
            icon="mdi:file-check",
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info, manual_availability=True)
        return HASensor(settings)

    def _publish_state(self) -> None:
        """Publish current state and attributes to HA."""
        try:
            self._ha_entity.set_state(self._state)
            self._ha_entity.set_attributes(self._attributes)
        except Exception as e:
            logger.warning("Failed to publish config status: %s", e)

    def _icon_for_state(self) -> str:
        """Return the appropriate icon for the current state."""
        return "mdi:file-check" if self._state == "valid" else "mdi:file-alert"

    def set_valid(self, added: int, removed: int, updated: int) -> None:
        """Mark config as valid after successful reload."""
        self._state = "valid"
        self._attributes["last_reload"] = datetime.now(timezone.utc).isoformat()
        self._attributes["last_error"] = None
        self._attributes["entities_added"] = added
        self._attributes["entities_removed"] = removed
        self._attributes["entities_updated"] = updated
        self._attributes["restart_reasons"] = []
        self._publish_state()

    def set_restart_required(
        self, added: int, removed: int, updated: int, reasons: list[str]
    ) -> None:
        """Mark config as requiring restart for some changes to take effect."""
        self._state = "restart_required"
        self._attributes["last_reload"] = datetime.now(timezone.utc).isoformat()
        self._attributes["last_error"] = None
        self._attributes["entities_added"] = added
        self._attributes["entities_removed"] = removed
        self._attributes["entities_updated"] = updated
        self._attributes["restart_reasons"] = reasons
        self._publish_state()

    def set_error(self, error_message: str) -> None:
        """Mark config as errored after failed reload."""
        self._state = "error"
        self._attributes["last_error"] = error_message
        self._attributes["last_error_time"] = datetime.now(timezone.utc).isoformat()
        self._publish_state()

    def republish(self) -> None:
        """Re-publish discovery config and state after MQTT reconnection."""
        try:
            self._ha_entity.write_config()
        except Exception as e:
            logger.warning("Failed to republish config status discovery: %s", e)
        self._publish_state()

    async def run(self) -> None:
        """No-op — this sensor is event-driven, not polled."""
        # ConfigStatusSensor doesn't poll; it's updated by ReloadManager
        # Keep the coroutine alive so it can be gathered with other entity tasks
        pass
