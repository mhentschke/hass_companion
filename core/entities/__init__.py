"""Unified entity package.

New entity classes live in submodules (base, fetcher, sensor, etc.).
Legacy classes are re-exported from _legacy for backward compatibility
until the old code is removed in task 11.
"""

from core.entities.base import BaseEntity
from core.entities.binary_sensor import BinarySensor, CommandBinarySensor
from core.entities.button import Button
from core.entities.fetcher import CommandFetcher, StateFetcher
from core.entities.interactive import InteractiveEntity
from core.entities.sensor import CommandSensor, Sensor
from core.entities.switch import Switch

# Re-export legacy classes so `import core.entities as core_entities` still works
from core.entities._legacy import (  # noqa: F401
    Button as LegacyButton,
    Entity,
    MultiPollingSensor,
    PollingSensor,
)

__all__ = [
    "BaseEntity",
    "BinarySensor",
    "Button",
    "CommandBinarySensor",
    "CommandFetcher",
    "CommandSensor",
    "InteractiveEntity",
    "Sensor",
    "StateFetcher",
    "Switch",
    # Legacy
    "LegacyButton",
    "Entity",
    "MultiPollingSensor",
    "PollingSensor",
]
