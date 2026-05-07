"""Linux platform implementation."""


class LinuxPlatform:
    """Linux-specific command builders and defaults."""

    def build_ping_command(
        self,
        host: str,
        timeout: float = 5.0,
        interface: str | None = None,
        size: int | None = None,
    ) -> list[str]:
        """Build ping command with Linux flags (-W takes seconds)."""
        cmd = ["ping", "-c", "1", "-W", str(int(timeout))]
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
            r"^veth",
            r"^docker",
            r"^br-",
            r"^virbr",
            r"^vnet",
            r"^lo$",
            r"^macvtap",
        ]

    @property
    def default_disk_includes(self) -> list[str]:
        return [r"^/dev/"]
