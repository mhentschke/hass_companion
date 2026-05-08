"""Thin subclasses of ha-mqtt-discoverable entities with retained availability.

The upstream library's set_availability() publishes without retain=True.
This causes a race condition: HA subscribes to the availability topic AFTER
the "online" message was already published, and since it's not retained,
HA never sees it — leaving the entity permanently "unavailable".

These subclasses override set_availability() to pass retain=True to the
library's own _update_state() method, which already supports the parameter.

This is the minimal fix — a 3-line override per class. If the library ever
adds retain support to set_availability(), these subclasses can be removed.
"""

from ha_mqtt_discoverable.sensors import BinarySensor as _HABinarySensor
from ha_mqtt_discoverable.sensors import Select as _HASelect
from ha_mqtt_discoverable.sensors import Sensor as _HASensor
from ha_mqtt_discoverable.sensors import Switch as _HASwitch


class Sensor(_HASensor):
    """Sensor with retained availability messages."""

    def set_availability(self, availability: bool) -> None:
        if not hasattr(self, "availability_topic"):
            raise RuntimeError("Manual availability is not configured for this entity!")
        message = "online" if availability else "offline"
        self._update_state(message, topic=self.availability_topic, retain=True)


class BinarySensor(_HABinarySensor):
    """BinarySensor with retained availability messages."""

    def set_availability(self, availability: bool) -> None:
        if not hasattr(self, "availability_topic"):
            raise RuntimeError("Manual availability is not configured for this entity!")
        message = "online" if availability else "offline"
        self._update_state(message, topic=self.availability_topic, retain=True)


class Switch(_HASwitch):
    """Switch with retained availability messages."""

    def set_availability(self, availability: bool) -> None:
        if not hasattr(self, "availability_topic"):
            raise RuntimeError("Manual availability is not configured for this entity!")
        message = "online" if availability else "offline"
        self._update_state(message, topic=self.availability_topic, retain=True)


class Select(_HASelect):
    """Select with retained availability messages."""

    def set_availability(self, availability: bool) -> None:
        if not hasattr(self, "availability_topic"):
            raise RuntimeError("Manual availability is not configured for this entity!")
        message = "online" if availability else "offline"
        self._update_state(message, topic=self.availability_topic, retain=True)
