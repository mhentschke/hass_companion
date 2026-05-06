"""Integration tests for async StateFetcher, CommandFetcher, and SystemFetcher."""

import asyncio

import pytest
from unittest.mock import Mock, patch

from core.entities.fetcher import CommandFetcher, StateFetcher, SystemFetcher
from core.config import SensorConfig


class TestStateFetcherAsync:
    """Tests for the async run() coroutine of StateFetcher."""

    @pytest.mark.asyncio
    async def test_poll_loop_executes_and_stops(self):
        """Verify run() polls and exits when stop() is called."""
        callback = Mock()

        class SimpleFetcher(StateFetcher):
            async def _fetch_value(self):
                return "hello"

        config = SensorConfig(
            name="Test", id="test", command="echo hi",
            polling_interval=0.05, parse=[],
        )
        fetcher = SimpleFetcher(config, callback, parser_configs=[])

        async def run_and_stop():
            task = asyncio.create_task(fetcher.run())
            await asyncio.sleep(0.15)
            fetcher._exit.set()
            await task

        await run_and_stop()
        assert callback.call_count >= 2
        callback.assert_called_with("hello")

    @pytest.mark.asyncio
    async def test_availability_tracking_marks_unavailable(self):
        """Verify fetcher marks unavailable after consecutive failures."""
        availability_cb = Mock()
        call_count = {"n": 0}

        class FailingFetcher(StateFetcher):
            async def _fetch_value(self):
                call_count["n"] += 1
                raise RuntimeError("always fails")

        config = SensorConfig(
            name="Test", id="test", command="fail",
            polling_interval=0.05, parse=[],
        )
        fetcher = FailingFetcher(
            config, Mock(), parser_configs=[],
            availability_callback=availability_cb,
        )

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.25)
        fetcher._exit.set()
        await task

        assert not fetcher.available
        availability_cb.assert_called_with(False)

    @pytest.mark.asyncio
    async def test_availability_recovery(self):
        """Verify fetcher recovers availability after failures then success."""
        availability_cb = Mock()
        call_count = {"n": 0}

        class RecoveringFetcher(StateFetcher):
            async def _fetch_value(self):
                call_count["n"] += 1
                if call_count["n"] <= 3:
                    raise RuntimeError("fail")
                return "ok"

        config = SensorConfig(
            name="Test", id="test", command="x",
            polling_interval=0.05, parse=[],
        )
        fetcher = RecoveringFetcher(
            config, Mock(), parser_configs=[],
            availability_callback=availability_cb,
        )

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.4)
        fetcher._exit.set()
        await task

        assert fetcher.available
        # Should have been called with False then True
        calls = [c[0][0] for c in availability_cb.call_args_list]
        assert False in calls
        assert True in calls


class TestCommandFetcherAsync:
    """Tests for CommandFetcher using async run_command."""

    @pytest.mark.asyncio
    async def test_fetches_command_output(self):
        """Verify CommandFetcher calls run_command and passes result to callback."""
        callback = Mock()
        config = SensorConfig(
            name="Test", id="test", command="echo 42",
            polling_interval=0.05, parse=[{"type": "int"}],
        )
        fetcher = CommandFetcher(config, callback, parser_configs=config.parse)

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.15)
        fetcher._exit.set()
        await task

        callback.assert_called_with(42)

    @pytest.mark.asyncio
    async def test_timeout_records_failure(self):
        """Verify CommandFetcher records failure on timeout."""
        callback = Mock()
        config = SensorConfig(
            name="Test", id="test", command="sleep 10",
            polling_interval=0.05, command_timeout=0.1, parse=[],
        )
        fetcher = CommandFetcher(config, callback, parser_configs=[])

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.3)
        fetcher._exit.set()
        await task

        callback.assert_not_called()
        assert fetcher._failure_count >= 1


class TestSystemFetcherAsync:
    """Tests for SystemFetcher using asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_callback_receives_raw_result(self):
        """SystemFetcher invokes callback with the callable's raw return value."""
        callback = Mock()
        fetcher = SystemFetcher(callback=callback, fn=lambda: 42, interval=0.05)

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.15)
        fetcher._exit.set()
        await task

        callback.assert_called_with(42)

    @pytest.mark.asyncio
    async def test_dict_result_passed_through(self):
        """SystemFetcher passes dict results directly to callback."""
        callback = Mock()
        fetcher = SystemFetcher(
            callback=callback,
            fn=lambda: {"cpu": 55.0, "mem": 1024},
            interval=0.05,
        )

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.15)
        fetcher._exit.set()
        await task

        callback.assert_called_with({"cpu": 55.0, "mem": 1024})

    @pytest.mark.asyncio
    async def test_exception_continues_polling(self):
        """SystemFetcher continues polling after callable raises."""
        call_count = {"n": 0}

        def flaky_fn():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("first call fails")
            return "recovered"

        callback = Mock()
        fetcher = SystemFetcher(callback=callback, fn=flaky_fn, interval=0.05)

        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.2)
        fetcher._exit.set()
        await task

        callback.assert_called_with("recovered")
