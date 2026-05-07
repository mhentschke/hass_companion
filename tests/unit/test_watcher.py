"""Unit tests for core.watcher — ConfigFileWatcher debounce logic."""

import asyncio
from unittest.mock import patch

import pytest

from core.watcher import ConfigFileWatcher


@pytest.mark.asyncio
class TestConfigFileWatcher:
    async def test_callback_fires_once_after_debounce(self):
        """Single mtime change triggers exactly one callback after debounce."""
        call_count = 0

        async def callback():
            nonlocal call_count
            call_count += 1

        stat_calls = 0

        def mock_stat(path):
            nonlocal stat_calls
            stat_calls += 1

            class Result:
                pass

            # First call is init. Change on second call (first poll).
            Result.st_mtime = 100.0 if stat_calls <= 1 else 200.0
            return Result()

        with patch("core.watcher.os.stat", side_effect=mock_stat):
            watcher = ConfigFileWatcher("/fake/config.yaml", callback, debounce=0.1)
            task = asyncio.create_task(watcher.run())

            # 1s for first poll + 0.1s debounce + margin
            await asyncio.sleep(1.5)
            watcher.stop()
            await asyncio.sleep(0.1)
            task.cancel()

        assert call_count == 1

    async def test_rapid_changes_result_in_single_callback(self):
        """Multiple mtime changes within debounce window trigger only one callback."""
        call_count = 0

        async def callback():
            nonlocal call_count
            call_count += 1

        # Simulate: initial=100, then changes to 200, then 300 during debounce, then stable
        stat_calls = 0

        def mock_stat(path):
            nonlocal stat_calls
            stat_calls += 1

            class Result:
                pass

            # First 2 calls: stable at 100
            # Calls 3-4: change to 200 (triggers debounce)
            # Calls 5-6: change to 300 (during debounce, resets it)
            # Calls 7+: stable at 300
            if stat_calls <= 2:
                Result.st_mtime = 100.0
            elif stat_calls <= 4:
                Result.st_mtime = 200.0
            else:
                Result.st_mtime = 300.0
            return Result()

        with patch("core.watcher.os.stat", side_effect=mock_stat):
            watcher = ConfigFileWatcher("/fake/config.yaml", callback, debounce=0.2)
            task = asyncio.create_task(watcher.run())

            await asyncio.sleep(3.0)
            watcher.stop()
            await asyncio.sleep(0.1)
            task.cancel()

        # Should fire at most once despite multiple mtime changes
        assert call_count == 1

    async def test_file_not_found_does_not_crash(self):
        """FileNotFoundError is handled gracefully without crashing."""
        call_count = 0

        async def callback():
            nonlocal call_count
            call_count += 1

        def mock_stat(path):
            raise FileNotFoundError("No such file")

        with patch("core.watcher.os.stat", side_effect=mock_stat):
            watcher = ConfigFileWatcher("/fake/config.yaml", callback, debounce=0.1)
            task = asyncio.create_task(watcher.run())

            await asyncio.sleep(1.5)
            watcher.stop()
            await asyncio.sleep(0.1)
            task.cancel()

        assert call_count == 0

    async def test_stop_exits_poll_loop(self):
        """Calling stop() causes run() to exit."""

        async def callback():
            pass

        def mock_stat(path):
            class Result:
                st_mtime = 100.0

            return Result()

        with patch("core.watcher.os.stat", side_effect=mock_stat):
            watcher = ConfigFileWatcher("/fake/config.yaml", callback, debounce=0.1)
            task = asyncio.create_task(watcher.run())

            await asyncio.sleep(0.5)
            watcher.stop()

            # Task should complete without needing cancel
            await asyncio.wait_for(task, timeout=2.0)
