"""Entity base classes — three-level hierarchy for single and composite entities.

BaseEntity: minimal root — stores mqtt/device context, provides stop().
Entity: 1:1 pattern — single config, single HA entity, creation hook + injection.
CompositeEntity: 1:N pattern — owns multiple HA entities and a fetcher.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BaseEntity:
    """Minimal shared contract for all entity types (single and composite).

    Stores MQTT settings and device context. Provides stop() for lifecycle management.
    Everything in the entity list has stop() and carries mqtt/device context.
    """

    def __init__(self, mqtt_settings, device):
        self._mqtt_settings = mqtt_settings
        self._device = device

    def start(self) -> None:
        """Start polling/processing. Backward compat bridge until async entry point."""
        pass

    def stop(self) -> None:
        """Clean shutdown. Subclasses should override to stop threads/tasks."""
        pass


class Entity(BaseEntity):
    """Single HA entity pattern (1:1). The standard entity type.

    Adds config storage, single _ha_entity, creation hook, and test injection.
    Subclasses must implement _create_ha_entity().
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(mqtt_settings, device)
        self._config = config
        self._ha_entity = _ha_entity or self._create_ha_entity()

    def _create_ha_entity(self):
        """Subclasses implement HA entity creation."""
        raise NotImplementedError


class CompositeEntity(BaseEntity):
    """Multiple HA entities from one source (1:N pattern).

    Owns a fetcher and a dict of HA entities. One poll cycle distributes
    values to N HA sensors. Subclasses provide the fetcher type and
    implement _create_ha_entities().
    """

    def __init__(
        self,
        mqtt_settings,
        device,
        *,
        name: str,
        unique_id: str,
        icon: str | None = None,
        units: dict[str, str] | None = None,
    ):
        super().__init__(mqtt_settings, device)
        self._base_name = name
        self._base_id = unique_id
        self._icon = icon
        self._units = units or {}
        self._ha_entities: dict[str, Any] = {}
        self._fetcher = None

    def _create_ha_entities(self, sample_result) -> None:
        """Create one HA sensor per key/index in the sample result.

        Subclasses must call this with a sample result from the callable
        to discover the shape and create HA entities accordingly.
        """
        raise NotImplementedError

    def start(self) -> None:
        """Start the fetcher in a background thread (backward compat bridge)."""
        if self._fetcher:
            self._fetcher.start()

    async def run(self) -> None:
        """Run the fetcher's async poll loop."""
        if self._fetcher:
            await self._fetcher.run()

    def _distribute_values(self, values) -> None:
        """Route each key's value to its corresponding HA entity."""
        if isinstance(values, dict):
            for key, value in values.items():
                if key in self._ha_entities:
                    self._ha_entities[key].set_state(value)
        elif isinstance(values, list):
            entity_list = list(self._ha_entities.values())
            for i, value in enumerate(values):
                if i < len(entity_list):
                    entity_list[i].set_state(value)

    def stop(self) -> None:
        """Stop the fetcher."""
        if self._fetcher:
            self._fetcher.stop()
