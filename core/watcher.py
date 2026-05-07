"""Configuration file watcher with debounce support."""

import asyncio
import logging
import os
from collections.abc import Callable

logger = logging.getLogger(__name__)


class ConfigFileWatcher:
    """Monitors a config file for modifications using os.stat() polling.

    Uses mtime polling (1-second interval) with a configurable debounce
    to avoid triggering multiple reloads during rapid edits.
    """

    def __init__(
        self,
        filepath: str,
        callback: Callable[[], asyncio.Future],
        debounce: float = 2.0,
    ):
        self._filepath = filepath
        self._callback = callback
        self._debounce = debounce
        self._running = False
        self._last_mtime: float | None = None

    async def run(self) -> None:
        """Poll file mtime every second, trigger callback after debounce."""
        self._running = True

        # Initialize last known mtime
        self._last_mtime = self._get_mtime()

        while self._running:
            await asyncio.sleep(1.0)

            if not self._running:
                break

            current_mtime = self._get_mtime()
            if current_mtime is None:
                continue

            if self._last_mtime is not None and current_mtime != self._last_mtime:
                logger.debug("Config file change detected, debouncing for %.1fs", self._debounce)
                self._last_mtime = current_mtime

                # Debounce: wait and check for additional changes
                await asyncio.sleep(self._debounce)

                if not self._running:
                    break

                # Check if file changed again during debounce
                final_mtime = self._get_mtime()
                while final_mtime is not None and final_mtime != self._last_mtime:
                    self._last_mtime = final_mtime
                    logger.debug("Additional change during debounce, resetting")
                    await asyncio.sleep(self._debounce)
                    if not self._running:
                        break
                    final_mtime = self._get_mtime()

                if not self._running:
                    break

                if final_mtime is not None:
                    self._last_mtime = final_mtime

                logger.debug("Debounce complete, triggering reload")
                await self._callback()
            elif current_mtime is not None:
                self._last_mtime = current_mtime

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False

    def _get_mtime(self) -> float | None:
        """Get file modification time, or None if file is inaccessible."""
        try:
            return os.stat(self._filepath).st_mtime
        except FileNotFoundError:
            logger.warning("Config file not found: %s", self._filepath)
            return None
        except OSError as e:
            logger.warning("Cannot stat config file %s: %s", self._filepath, e)
            return None
