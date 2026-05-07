"""Unit tests for core.subprocess — async command execution utility."""

import pytest

from core.subprocess import CommandFailed, CommandTimeout, run_command


@pytest.mark.asyncio
class TestRunCommand:
    async def test_successful_command_returns_stdout(self):
        result = await run_command("echo hello")
        assert result == "hello"

    async def test_strips_trailing_newline(self):
        result = await run_command("printf 'no newline'")
        assert result == "no newline"

    async def test_timeout_raises_command_timeout(self):
        with pytest.raises(CommandTimeout):
            await run_command("sleep 10", timeout=0.1)

    async def test_execution_failure_raises_command_failed(self):
        with pytest.raises(CommandFailed):
            await run_command("echo hello", shell="/nonexistent/shell")
