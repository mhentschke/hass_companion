"""macOS (Darwin) platform implementation."""


class DarwinPlatform:
    """macOS-specific command builders and defaults."""

    def build_ping_command(
        self,
        host: str,
        timeout: float = 5.0,
        interface: str | None = None,
        size: int | None = None,
    ) -> list[str]:
        """Build ping command with macOS flags (-W takes milliseconds)."""
        cmd = ["ping", "-c", "1", "-W", str(int(timeout * 1000))]
        if interface:
            cmd += ["-I", interface]
        if size:
            cmd += ["-s", str(size)]
        cmd.append(host)
        return cmd

    def build_dns_command(self, host: str) -> list[str]:
        """Build dig command."""
        return ["dig", host]

    @property
    def default_shell(self) -> str:
        return "/bin/bash"

    @property
    def default_network_excludes(self) -> list[str]:
        return [
            r"^utun",
            r"^awdl",
            r"^llw",
            r"^bridge",
            r"^lo0$",
            r"^gif",
            r"^stf",
            r"^ap",
        ]

    @property
    def default_disk_includes(self) -> list[str]:
        return [r"^/dev/disk"]
