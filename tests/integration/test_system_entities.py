"""Integration tests for SystemFetcher and SystemMultiSensor."""

import asyncio
from unittest.mock import Mock

import pytest

from core.entities.fetcher import SystemFetcher
from core.entities.system import SystemMultiSensor


class TestSystemFetcher:
    """Tests for SystemFetcher with mock callables."""

    @pytest.mark.asyncio
    async def test_callback_receives_raw_result(self):
        """SystemFetcher invokes callback with the callable's raw return value."""
        callback = Mock()
        fetcher = SystemFetcher(
            callback=callback,
            fn=lambda: 42,
            interval=0.1,
        )
        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.25)
        fetcher.stop()
        await task

        callback.assert_called_with(42)

    @pytest.mark.asyncio
    async def test_dict_result_passed_through(self):
        """SystemFetcher passes dict results directly to callback."""
        callback = Mock()
        fetcher = SystemFetcher(
            callback=callback,
            fn=lambda: {"cpu": 55.0, "mem": 1024},
            interval=0.1,
        )
        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.25)
        fetcher.stop()
        await task

        callback.assert_called_with({"cpu": 55.0, "mem": 1024})

    @pytest.mark.asyncio
    async def test_exception_handling_continues_polling(self):
        """SystemFetcher continues polling after callable raises."""
        call_count = {"n": 0}

        def flaky_fn():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("first call fails")
            return "recovered"

        callback = Mock()
        fetcher = SystemFetcher(
            callback=callback,
            fn=flaky_fn,
            interval=0.1,
        )
        task = asyncio.create_task(fetcher.run())
        await asyncio.sleep(0.35)
        fetcher.stop()
        await task

        # Should have recovered and called back with "recovered"
        callback.assert_called_with("recovered")


class TestSystemMultiSensor:
    """Tests for SystemMultiSensor with mock callables and HA entities."""

    @pytest.mark.asyncio
    async def test_dict_result_distributes_to_ha_entities(self):
        """Each key in a dict result routes to its corresponding mock HA entity."""
        mock_temp = Mock()
        mock_humidity = Mock()
        mock_entities = {"temp": mock_temp, "humidity": mock_humidity}

        sensor = SystemMultiSensor(
            None,
            None,
            name="Test",
            unique_id="test",
            fn=lambda: {"temp": 42.0, "humidity": 65},
            interval=0.1,
            _ha_entities=mock_entities,
        )
        task = asyncio.create_task(sensor.run())
        await asyncio.sleep(0.25)
        sensor.stop()
        await task

        mock_temp.set_state.assert_called_with(42.0)
        mock_humidity.set_state.assert_called_with(65)

    @pytest.mark.asyncio
    async def test_list_result_distributes_to_ha_entities(self):
        """Each index in a list result routes to its corresponding mock HA entity."""
        mock_0 = Mock()
        mock_1 = Mock()
        mock_2 = Mock()
        mock_entities = {"0": mock_0, "1": mock_1, "2": mock_2}

        sensor = SystemMultiSensor(
            None,
            None,
            name="CPU",
            unique_id="cpu",
            fn=lambda: [10.0, 20.0, 30.0],
            interval=0.1,
            _ha_entities=mock_entities,
        )
        task = asyncio.create_task(sensor.run())
        await asyncio.sleep(0.25)
        sensor.stop()
        await task

        mock_0.set_state.assert_called_with(10.0)
        mock_1.set_state.assert_called_with(20.0)
        mock_2.set_state.assert_called_with(30.0)
