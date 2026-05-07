"""Platform abstraction base — Protocol defining the platform interface.

Each supported OS implements this protocol to provide platform-specific
command construction and default filter patterns.
"""

from typing import Protocol


class PlatformCommands(Protocol):
    """Platform-specific command builders and defaults."""

    def build_ping_command(
        self,
        host: str,
        timeout: float = 5.0,
        interface: str | None = None,
        size: int | None = None,
    ) -> list[str]:
        """Build a ping command for the current platform."""
        ...

    def build_dns_command(self, host: str) -> list[str]:
        """Build a DNS lookup command for the current platform."""
        ...

    @property
    def default_shell(self) -> str:
        """Default shell path for subprocess execution."""
        ...

    @property
    def default_network_excludes(self) -> list[str]:
        """Regex patterns for network interfaces to exclude by default."""
        ...

    @property
    def default_disk_includes(self) -> list[str]:
        """Regex patterns for disk devices to include by default."""
        ...
