"""InteractiveEntity — base for entities that receive commands and optionally poll state.

Shared by Switch, Select, and future interactive entity types (Number, Text).
Extends Entity with MQTT command subscription and optional state feedback
via a composed StateFetcher.
"""

import logging
from typing import Any

from core.entities.base import Entity
from core.entities.fetcher import StateFetcher

logger = logging.getLogger(__name__)


class InteractiveEntity(Entity):
    """Base for entities that receive MQTT commands and optionally poll state feedback.

    Subclasses implement:
    - _setup_feedback(): create a StateFetcher for state feedback (optional)
    - _execute_action(payload): handle incoming command
    - _update_state(value): update the HA entity state
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)
        self._feedback_fetcher: StateFetcher | None = None
        self._setup_feedback()
        if self._feedback_fetcher:
            self._feedback_fetcher.start()

    def _setup_feedback(self) -> None:
        """Subclasses create a feedback fetcher if config specifies one."""
        pass

    def _execute_action(self, payload: str) -> None:
        """Subclasses implement the action for incoming commands."""
        raise NotImplementedError

    def _on_feedback(self, value: Any) -> None:
        """Callback from feedback fetcher — update own HA state."""
        self._update_state(value)

    def _update_state(self, value: Any) -> None:
        """Subclasses implement state update on their HA entity."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop feedback fetcher if present."""
        if self._feedback_fetcher:
            self._feedback_fetcher.stop()
