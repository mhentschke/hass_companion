"""Thin subclasses of ha-mqtt-discoverable entities with retained availability and LWT support.

Two concerns addressed here:

1. Retained per-entity availability: The upstream library's set_availability() publishes
   without retain=True, causing a race condition where HA misses the "online" message.
   We override set_availability() to pass retain=True.

2. Device-level availability via LWT: All entities include a shared device status topic
   in their discovery config alongside their per-entity availability topic. This allows
   the MQTT broker's Last Will and Testament to mark all entities unavailable when the
   app crashes or stops.

   Discovery config emits:
     availability:
       - topic: hmd/{device_id}/status          (device-level, LWT-backed)
       - topic: hmd/sensor/.../availability     (per-entity, fetcher-backed)
     availability_mode: all

   Both must be "online" for HA to consider the entity available.
"""

from typing import Any

from ha_mqtt_discoverable.sensors import BinarySensor as _HABinarySensor
from ha_mqtt_discoverable.sensors import Select as _HASelect
from ha_mqtt_discoverable.sensors import Sensor as _HASensor
from ha_mqtt_discoverable.sensors import Switch as _HASwitch

# Set once at app startup via configure_device_status_topic().
# All entity subclasses reference this to build their availability list.
_device_status_topic: str | None = None


def configure_device_status_topic(topic: str) -> None:
    """Set the shared device status topic for all entity subclasses.

    Must be called before any entities are created. Typically called once
    at app startup with: hmd/{device_id}/status
    """
    global _device_status_topic
    _device_status_topic = topic


def get_device_status_topic() -> str | None:
    """Get the configured device status topic."""
    return _device_status_topic


class _RetainedAvailabilityMixin:
    """Mixin providing retained state/availability and hybrid availability config.

    Overrides:
    - _update_state(): defaults retain=True for state and availability messages.
      This prevents race conditions where HA subscribes to topics after the message
      was published. Retained messages are replayed to new subscribers by the broker.
    - generate_config(): emits availability list (device + entity) with mode=all
    """

    def _update_state(self, state, topic=None, last_reset=None, retain=True, force_update=False):
        """Override to default retain=True for all state publishes.

        The upstream library defaults retain=False, which causes HA to miss messages
        published before it subscribes to the topic (race condition on entity creation).
        Retained messages solve this: the broker replays them to new subscribers.
        """
        return super()._update_state(
            state, topic=topic, last_reset=last_reset, retain=retain, force_update=force_update
        )

    def set_availability(self, availability: bool) -> None:
        if not hasattr(self, "availability_topic"):
            raise RuntimeError("Manual availability is not configured for this entity!")
        message = "online" if availability else "offline"
        self._update_state(message, topic=self.availability_topic, retain=True)

    def generate_config(self) -> dict[str, Any]:
        config = super().generate_config()
        if _device_status_topic and hasattr(self, "availability_topic"):
            # Replace single availability_topic with HA's availability list format.
            # Both device-level AND entity-level must be "online" for entity to be available.
            config.pop("availability_topic", None)
            config["availability"] = [
                {"topic": _device_status_topic},
                {"topic": self.availability_topic},
            ]
            config["availability_mode"] = "all"
        elif _device_status_topic:
            # No per-entity availability — use device status topic alone
            config["availability_topic"] = _device_status_topic
        return config


class Sensor(_RetainedAvailabilityMixin, _HASensor):
    """Sensor with retained availability and device-level LWT support."""

    pass


class BinarySensor(_RetainedAvailabilityMixin, _HABinarySensor):
    """BinarySensor with retained availability and device-level LWT support."""

    pass


class Switch(_RetainedAvailabilityMixin, _HASwitch):
    """Switch with retained availability and device-level LWT support."""

    pass


class Select(_RetainedAvailabilityMixin, _HASelect):
    """Select with retained availability and device-level LWT support."""

    pass
