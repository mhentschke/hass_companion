"""Unified entity package.

Each entity type is a single class owning both internal logic and HA representation.
"""

from core.entities.base import BaseEntity, CompositeEntity, Entity
from core.entities.binary_sensor import BinarySensor, CommandBinarySensor
from core.entities.button import Button
from core.entities.fetcher import CommandFetcher, StateFetcher, SystemFetcher
from core.entities.interactive import InteractiveEntity
from core.entities.select import Select
from core.entities.sensor import CommandSensor, Sensor, SystemSensor
from core.entities.switch import Switch
from core.entities.system import SystemMultiSensor, create_system_entities

__all__ = [
    "BaseEntity",
    "BinarySensor",
    "Button",
    "CommandBinarySensor",
    "CommandFetcher",
    "CommandSensor",
    "CompositeEntity",
    "Entity",
    "InteractiveEntity",
    "Select",
    "Sensor",
    "StateFetcher",
    "Switch",
    "SystemFetcher",
    "SystemMultiSensor",
    "SystemSensor",
    "create_system_entities",
]
