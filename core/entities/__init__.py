"""Unified entity package.

New entity classes live in submodules (base, fetcher, sensor, etc.).
Legacy classes are re-exported from _legacy for backward compatibility
until the old code is removed in task 11.
"""

from core.entities.base import BaseEntity
from core.entities.binary_sensor import BinarySensor, CommandBinarySensor
from core.entities.fetcher import CommandFetcher, StateFetcher
from core.entities.sensor import CommandSensor, Sensor

# Re-export legacy classes so `import core.entities as core_entities` still works
from core.entities._legacy import (  # noqa: F401
    Button,
    Entity,
    MultiPollingSensor,
    PollingSensor,
)

__all__ = [
    "BaseEntity",
    "BinarySensor",
    "CommandBinarySensor",
    "CommandFetcher",
    "CommandSensor",
    "Sensor",
    "StateFetcher",
    # Legacy
    "Button",
    "Entity",
    "MultiPollingSensor",
    "PollingSensor",
]
