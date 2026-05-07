"""InteractiveEntity — base for entities that receive commands and optionally poll state.

Shared by Switch, Select, and future interactive entity types (Number, Text).
Extends Entity with MQTT command subscription, asyncio.Queue for command dispatch,
and optional state feedback via a composed StateFetcher.
"""

import asyncio
import logging
from typing import Any

from core.entities.base import Entity
from core.entities.fetcher import StateFetcher

logger = logging.getLogger(__name__)


class InteractiveEntity(Entity):
    """Base for entities that receive MQTT commands and optionally poll state feedback.

    Uses an asyncio.Queue for thread-safe dispatch from MQTT callbacks to the
    async command handler. The run() coroutine gathers command handling and
    optional feedback polling.

    Subclasses implement:
    - _setup_feedback(): create a StateFetcher for state feedback (optional)
    - _execute_action(payload): handle incoming command (async)
    - _update_state(value): update the HA entity state
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._exit = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._feedback_fetcher: StateFetcher | None = None
        self._setup_feedback()

    def _setup_feedback(self) -> None:
        """Subclasses create a feedback fetcher if config specifies one."""
        pass

    async def run(self) -> None:
        """Concurrently handle commands and poll feedback."""
        self._loop = asyncio.get_running_loop()
        # If no feedback fetcher, publish available immediately (optimistic mode)
        if not self._feedback_fetcher and hasattr(self._ha_entity, "set_availability"):
            self._ha_entity.set_availability(True)
        tasks = [self._handle_commands()]
        if self._feedback_fetcher:
            tasks.append(self._feedback_fetcher.run())
        await asyncio.gather(*tasks)

    async def _handle_commands(self) -> None:
        """Process commands from the queue until shutdown."""
        while not self._exit.is_set():
            try:
                payload = await asyncio.wait_for(self._command_queue.get(), timeout=1.0)
                await self._execute_action(payload)
            except asyncio.TimeoutError:
                continue

    def _dispatch_command(self, payload: str) -> None:
        """Thread-safe dispatch of command payload to the async queue.

        Called from MQTT callbacks which run on paho-mqtt's internal thread.
        """
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._command_queue.put_nowait, payload)
        else:
            # Fallback: direct put (works if called from same event loop or tests)
            try:
                self._command_queue.put_nowait(payload)
            except Exception:
                logger.warning("Failed to dispatch command: no running event loop")

    async def _execute_action(self, payload: str) -> None:
        """Subclasses implement the action for incoming commands."""
        raise NotImplementedError

    def _on_feedback(self, value: Any) -> None:
        """Callback from feedback fetcher — update own HA state."""
        self._update_state(value)

    def _update_state(self, value: Any) -> None:
        """Subclasses implement state update on their HA entity."""
        raise NotImplementedError

    def stop(self) -> None:
        """Signal shutdown and stop feedback fetcher."""
        self._exit.set()
        if self._feedback_fetcher:
            self._feedback_fetcher.stop()
