"""Unified entity package.

Each entity type is a single class owning both internal logic and HA representation.
"""

from core.entities.base import BaseEntity
from core.entities.binary_sensor import BinarySensor, CommandBinarySensor
from core.entities.button import Button
from core.entities.fetcher import CommandFetcher, StateFetcher
from core.entities.interactive import InteractiveEntity
from core.entities.select import Select
from core.entities.sensor import CommandSensor, Sensor
from core.entities.switch import Switch

__all__ = [
    "BaseEntity",
    "BinarySensor",
    "Button",
    "CommandBinarySensor",
    "CommandFetcher",
    "CommandSensor",
    "InteractiveEntity",
    "Select",
    "Sensor",
    "StateFetcher",
    "Switch",
]
