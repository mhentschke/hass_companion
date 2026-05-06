"""Button entity — executes a command on press, no polling or state feedback.

Button extends Entity directly. It subscribes to MQTT press commands
and executes a shell command when triggered. Uses an asyncio.Queue for
thread-safe dispatch from MQTT callbacks.
"""

import asyncio
import logging

from core.entities.base import Entity
from core.subprocess import CommandFailed, CommandTimeout, run_command

logger = logging.getLogger(__name__)

DEFAULT_BUTTON_TIMEOUT = 30.0


class Button(Entity):
    """Button entity that executes a command on press.

    No polling, no fetcher, no state feedback. Uses an asyncio.Queue to
    dispatch press commands from the MQTT callback thread to the async handler.
    """

    def __init__(self, config, mqtt_settings, device, *, _ha_entity=None):
        super().__init__(config, mqtt_settings, device, _ha_entity=_ha_entity)
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._exit = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        # Buttons have no state, so ha-mqtt-discoverable won't auto-publish
        # the discovery config. We must call write_config() explicitly.
        self._ha_entity.write_config()

    def _create_ha_entity(self):
        """Create HA button entity via ha-mqtt-discoverable."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Button as HAButton,
            ButtonInfo as HAButtonInfo,
        )

        entity_info = HAButtonInfo(
            name=self._config.name,
            unique_id=self._config.id or self._config.name,
            device=self._device,
            icon=self._config.icon,
        )
        settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info)
        return HAButton(settings, self._on_press)

    async def run(self) -> None:
        """Wait for press commands from the queue until shutdown."""
        self._loop = asyncio.get_running_loop()
        while not self._exit.is_set():
            try:
                await asyncio.wait_for(
                    self._command_queue.get(), timeout=1.0
                )
                await self._execute_press()
            except asyncio.TimeoutError:
                continue

    def _on_press(self, client, user_data, message) -> None:
        """MQTT callback when button is pressed — dispatch to async queue."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._command_queue.put_nowait, "press")
        else:
            # Fallback for synchronous callers / tests
            try:
                self._command_queue.put_nowait("press")
            except Exception:
                logger.warning("Failed to dispatch button press: no running event loop")

    async def _execute_press(self) -> None:
        """Execute the configured command asynchronously."""
        command = self._config.command
        shell = self._config.shell
        timeout = getattr(self._config, "command_timeout", DEFAULT_BUTTON_TIMEOUT)

        try:
            await run_command(command, shell, timeout)
        except CommandTimeout:
            logger.warning(
                "Button '%s' command timed out after %ss: %s",
                self._config.name,
                timeout,
                command,
            )
        except CommandFailed as e:
            logger.error(
                "Button '%s' command failed: %s",
                self._config.name,
                e,
            )

    def stop(self) -> None:
        """Signal the run loop to exit."""
        self._exit.set()
