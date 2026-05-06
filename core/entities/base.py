"""Base entity class — common interface for all unified entity types."""

import logging

logger = logging.getLogger(__name__)


class BaseEntity:
    """Common interface for all entity types.

    Handles HA entity creation and provides a stop() method for clean shutdown.
    Subclasses must implement _create_ha_entity().
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        self._config = config
        self._mqtt_settings = mqtt_settings
        self._device = device
        self._ha_entity = _ha_entity or self._create_ha_entity()

    def _create_ha_entity(self):
        """Subclasses implement HA entity creation."""
        raise NotImplementedError

    def stop(self) -> None:
        """Clean shutdown. Subclasses should override to stop threads/tasks."""
        pass
