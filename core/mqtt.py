"""MQTT reconnection manager — monitors connection and handles reconnection with backoff.

Runs as an async coroutine alongside entity tasks. On disconnect, attempts
reconnection with exponential backoff (1s → 2s → 4s → ... → 60s max).
On reconnect, triggers republishing of discovery and state for all entities.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 60.0


class MQTTReconnectionManager:
    """Monitors MQTT connection state and handles reconnection with exponential backoff.

    On reconnect, iterates all entities and calls republish() to re-send
    discovery configs and last known state.

    Accepts either a dict (entity registry) or list of entities. When a dict
    is passed, iterates .values() — this keeps the manager in sync with
    registry mutations during hot-reload.
    """

    def __init__(
        self,
        mqtt_client: Any,
        entities: Any,
        *,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
    ):
        self._client = mqtt_client
        self._entities = entities
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._backoff = initial_backoff
        self._shutdown = asyncio.Event()
        self._was_connected = True  # Assume we start connected

    def _iter_entities(self):
        """Iterate entities regardless of whether stored as dict or list."""
        if isinstance(self._entities, dict):
            return self._entities.values()
        return self._entities

    async def run(self) -> None:
        """Monitor connection state, reconnect with exponential backoff on disconnect."""
        while not self._shutdown.is_set():
            connected = self._client.is_connected()

            if connected and not self._was_connected:
                # Just reconnected
                logger.info("MQTT connection re-established")
                self._backoff = self._initial_backoff
                self._was_connected = True
                await self._republish_all()

            elif not connected and self._was_connected:
                # Just disconnected
                logger.warning("MQTT connection lost, will attempt reconnection")
                self._was_connected = False
                await self._reconnect_loop()

            # Poll connection state every second
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=1.0)
                break  # Shutdown was set
            except asyncio.TimeoutError:
                pass

    async def _reconnect_loop(self) -> None:
        """Attempt reconnection with exponential backoff until success or shutdown."""
        while not self._shutdown.is_set():
            logger.debug("Attempting MQTT reconnection (backoff: %.1fs)", self._backoff)
            try:
                self._client.reconnect()
                # Give paho-mqtt a moment to establish the connection
                await asyncio.sleep(0.5)
                if self._client.is_connected():
                    logger.info("MQTT reconnected successfully")
                    self._backoff = self._initial_backoff
                    self._was_connected = True
                    await self._republish_all()
                    return
            except Exception as e:
                logger.warning("MQTT reconnection failed: %s", e)

            # Wait with backoff before next attempt
            logger.debug("Retrying MQTT reconnection in %.1fs", self._backoff)
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self._backoff)
                return  # Shutdown was set during wait
            except asyncio.TimeoutError:
                pass

            # Exponential backoff
            self._backoff = min(self._backoff * 2, self._max_backoff)

    async def _republish_all(self) -> None:
        """Re-publish discovery and last known state for all entities."""
        entities = list(self._iter_entities())
        logger.debug("Republishing discovery and state for %d entities", len(entities))
        for entity in entities:
            if hasattr(entity, "republish"):
                try:
                    entity.republish()
                except Exception as e:
                    logger.warning("Failed to republish entity: %s", e)

    def stop(self) -> None:
        """Signal the reconnection manager to stop."""
        self._shutdown.set()
