"""StateFetcher — standalone polling component with parser pipeline.

Not an HA entity itself. Used by Sensor (as its core) and InteractiveEntity
(for state feedback). Owns the polling thread, parser pipeline, availability
tracking, and invokes a callback with parsed values.
"""

import logging
import subprocess
import threading
from typing import Any, Callable

from core.parsers import build_pipeline

logger = logging.getLogger(__name__)


class StateFetcher:
    """Polls a value source at a configurable interval, applies parsers, invokes callback.

    Subclasses implement _fetch_value() to provide the raw value.
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
        self._exit = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure_count = 0
        self._failure_threshold = 3
        self._available = True

    def _fetch_value(self) -> str:
        """Subclasses implement value retrieval. Returns raw string."""
        raise NotImplementedError

    def start(self) -> None:
        """Start the polling thread."""
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to exit."""
        self._exit.set()

    def _poll_loop(self) -> None:
        """Polling loop running in a daemon thread."""
        while not self._exit.is_set():
            self._execute_poll()
            self._exit.wait(timeout=self._interval)

    def _execute_poll(self) -> None:
        """Fetch value, apply parsers, invoke callback."""
        try:
            raw = self._fetch_value()
            output: Any = raw
            for parser in self._pipeline:
                output = parser.parse(output)
            self._callback(output)
            self._record_success()
        except Exception as e:
            logger.error("Fetch failed: %s", e)
            self._record_failure()

    def _record_success(self) -> None:
        """Reset failure count and mark available if previously unavailable."""
        self._failure_count = 0
        if not self._available:
            self._available = True
            logger.info("Fetcher is now available")
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
    """Fetches value by executing a shell command via subprocess."""

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

    def _fetch_value(self) -> str:
        """Execute shell command and return stdout."""
        try:
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-c", self._command],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return result.stdout.rstrip("\n")
        except subprocess.TimeoutExpired:
            logger.warning("Command timed out: %s", self._command)
            raise
        except Exception as e:
            logger.error("Command failed: %s — %s", self._command, e)
            raise


class SystemFetcher(StateFetcher):
    """Fetches value by calling a Python callable (e.g., psutil function).

    Unlike CommandFetcher which runs a subprocess, SystemFetcher invokes
    a Python function directly. The function can return any type (scalar,
    dict, list) — the parser pipeline is skipped since system callables
    already return typed data.
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

    def _fetch_value(self) -> Any:
        """Call the Python function and return its raw result."""
        return self._fn()

    def _execute_poll(self) -> None:
        """Fetch value and invoke callback directly (no parser pipeline)."""
        try:
            result = self._fetch_value()
            self._callback(result)
            self._record_success()
        except Exception as e:
            logger.error("System fetch failed: %s", e)
            self._record_failure()
