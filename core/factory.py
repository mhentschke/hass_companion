"""Entity factory — maps entity type strings to entity classes.

Provides a single entry point for creating entities from config objects.
"""

import logging
from typing import Any

from core.entities.base import Entity
from core.entities.binary_sensor import CommandBinarySensor
from core.entities.button import Button
from core.entities.select import Select
from core.entities.sensor import CommandSensor
from core.entities.switch import Switch

logger = logging.getLogger(__name__)

_ENTITY_REGISTRY: dict[str, type[Entity]] = {
    "sensor": CommandSensor,
    "binary_sensor": CommandBinarySensor,
    "button": Button,
    "switch": Switch,
    "select": Select,
}


def create_entity(
    entity_type: str,
    config: Any,
    mqtt_settings: Any,
    device: Any,
) -> Entity:
    """Create a fully constructed entity instance from type string and config.

    Args:
        entity_type: One of 'sensor', 'binary_sensor', 'button', 'switch', 'select'.
        config: Pydantic config model for the entity.
        mqtt_settings: MQTT connection settings (HASettings.MQTT instance).
        device: HA DeviceInfo instance for the entity.

    Returns:
        A fully constructed entity instance.

    Raises:
        ValueError: If entity_type is not recognized.
    """
    cls = _ENTITY_REGISTRY.get(entity_type)
    if cls is None:
        raise ValueError(
            f"Unknown entity type: '{entity_type}'. Valid types: {', '.join(sorted(_ENTITY_REGISTRY.keys()))}"
        )
    return cls(config, mqtt_settings, device)
