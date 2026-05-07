"""StateFetcher — standalone async polling component with parser pipeline.

Not an HA entity itself. Used by Sensor (as its core) and InteractiveEntity
(for state feedback). Owns the poll loop as an async coroutine, parser pipeline,
availability tracking, and invokes a callback with parsed values.
"""

import asyncio
import logging
from typing import Any, Callable

from core.parsers import build_pipeline
from core.subprocess import run_command

logger = logging.getLogger(__name__)


class StateFetcher:
    """Polls a value source at a configurable interval, applies parsers, invokes callback.

    Subclasses implement _fetch_value() to provide the raw value.
    The poll loop runs as an async coroutine via run().
    """

    def __init__(
        self,
        config,
        callback: Callable[[Any], None],
        *,
        parser_configs=None,
        availability_callback: Callable[[bool], None] | None = None,
        interval: float | None = None,
    ):
        self._config = config
        self._callback = callback
        self._availability_callback = availability_callback
        # Use explicit interval if provided, otherwise resolve from config
        if interval is not None:
            self._interval = interval
        else:
            self._interval = config.get_polling_interval(10.0)
        self._pipeline = build_pipeline(parser_configs or [])
        self._exit = asyncio.Event()
        self._failure_count = 0
        self._failure_threshold = 3
        self._available = False  # Start as unavailable; first success publishes online

    async def _fetch_value(self) -> Any:
        """Subclasses implement value retrieval. Returns raw value."""
        raise NotImplementedError

    async def run(self) -> None:
        """Async poll loop — the primary interface for async callers."""
        while not self._exit.is_set():
            await self._execute_poll()
            try:
                await asyncio.wait_for(self._exit.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass  # Normal — timeout means "time to poll again"

    def stop(self) -> None:
        """Signal the poll loop to exit."""
        self._exit.set()

    async def _execute_poll(self) -> None:
        """Fetch value, apply parsers, invoke callback."""
        try:
            raw = await self._fetch_value()
            output: Any = raw
            for parser in self._pipeline:
                output = parser.parse(output)
            self._callback(output)
            self._record_success()
        except Exception as e:
            logger.warning("Fetch failed: %s", e)
            self._record_failure()

    def _record_success(self) -> None:
        """Reset failure count and mark available if previously unavailable."""
        self._failure_count = 0
        if not self._available:
            self._available = True
            logger.debug("Fetcher is now available")
            if self._availability_callback:
                self._availability_callback(True)

    def _record_failure(self) -> None:
        """Increment failure count and mark unavailable if threshold reached."""
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold and self._available:
            self._available = False
            logger.warning(
                "Fetcher is now unavailable after %d consecutive failures",
                self._failure_count,
            )
            if self._availability_callback:
                self._availability_callback(False)

    @property
    def available(self) -> bool:
        return self._available


class CommandFetcher(StateFetcher):
    """Fetches value by executing a shell command via async subprocess."""

    def __init__(
        self,
        config,
        callback: Callable[[Any], None],
        *,
        parser_configs=None,
        availability_callback: Callable[[bool], None] | None = None,
    ):
        super().__init__(config, callback, parser_configs=parser_configs, availability_callback=availability_callback)
        self._command = config.command
        self._timeout = config.command_timeout
        self._shell = getattr(config, "shell", "bash")

    async def _fetch_value(self) -> str:
        """Execute shell command asynchronously and return stdout."""
        return await run_command(self._command, self._shell, self._timeout)


class SystemFetcher(StateFetcher):
    """Fetches value by calling a Python callable via asyncio.to_thread().

    Unlike CommandFetcher which runs a subprocess, SystemFetcher invokes
    a Python function in a thread pool to avoid blocking the event loop.
    The parser pipeline is skipped since system callables already return typed data.
    """

    def __init__(
        self,
        callback: Callable[[Any], None],
        *,
        fn: Callable,
        interval: float,
        availability_callback: Callable[[bool], None] | None = None,
    ):
        # Pass config=None, interval explicitly — system entities don't use config objects
        super().__init__(
            config=None,
            callback=callback,
            parser_configs=None,
            availability_callback=availability_callback,
            interval=interval,
        )
        self._fn = fn

    async def _fetch_value(self) -> Any:
        """Call the Python function in a thread pool and return its raw result."""
        return await asyncio.to_thread(self._fn)

    async def _execute_poll(self) -> None:
        """Fetch value and invoke callback directly (no parser pipeline)."""
        try:
            result = await self._fetch_value()
            self._callback(result)
            self._record_success()
        except Exception as e:
            logger.warning("System fetch failed: %s", e)
            self._record_failure()
