"""Shared async command execution utility.

Provides a single async function for executing shell commands, used by all
entities that run subprocesses (CommandFetcher, Switch, Button, Select).
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


class CommandTimeout(Exception):
    """Raised when a shell command exceeds its timeout."""

    pass


class CommandFailed(Exception):
    """Raised when a shell command fails to execute."""

    pass


async def run_command(
    command: str,
    shell: str = "bash",
    timeout: float = 30.0,
) -> str:
    """Execute a shell command asynchronously and return stdout.

    Args:
        command: Shell command string to execute.
        shell: Shell binary to use (default: bash).
        timeout: Maximum execution time in seconds.

    Returns:
        Command stdout with trailing newline stripped.

    Raises:
        CommandTimeout: If command exceeds timeout.
        CommandFailed: If command cannot be executed.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            shell,
            "--noprofile",
            "--norc",
            "-c",
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode().rstrip("\n")
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("Command timed out after %ss: %s", timeout, command)
        raise CommandTimeout(f"Command timed out after {timeout}s: {command}")
    except OSError as e:
        logger.error("Command failed: %s — %s", command, e)
        raise CommandFailed(f"Command failed: {command} — {e}")
