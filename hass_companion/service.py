"""Service installation backends for hass-companion.

Provides platform-specific service management (install/uninstall/status)
for systemd (Linux) and launchd (macOS).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


SERVICE_NAME = "hass-companion"
LAUNCHD_LABEL = "com.hass-companion"


@dataclass
class ServiceStatus:
    """Status of the installed service."""

    installed: bool
    enabled: bool
    running: bool
    unit_path: Path | None = None
    binary_path: str | None = None


class PlatformBackend(ABC):
    """Abstract base for platform-specific service operations."""

    @abstractmethod
    def install(self, binary_path: str, config_path: str, user: bool) -> None: ...

    @abstractmethod
    def uninstall(self, user: bool) -> None: ...

    @abstractmethod
    def status(self) -> ServiceStatus: ...


class SystemdBackend(PlatformBackend):
    """Linux systemd service backend."""

    SYSTEM_UNIT_DIR = Path("/etc/systemd/system")
    USER_UNIT_DIR = Path.home() / ".config/systemd/user"

    def _unit_path(self, user: bool) -> Path:
        base = self.USER_UNIT_DIR if user else self.SYSTEM_UNIT_DIR
        return base / f"{SERVICE_NAME}.service"

    def _generate_unit(self, binary_path: str, config_path: str, user: bool) -> str:
        wanted_by = "default.target" if user else "multi-user.target"
        return textwrap.dedent(f"""\
            [Unit]
            Description=Hass Companion — Home Assistant MQTT Companion
            After=network-online.target
            Wants=network-online.target

            [Service]
            Type=simple
            ExecStart={binary_path} --config {config_path}
            Restart=on-failure
            RestartSec=10

            [Install]
            WantedBy={wanted_by}
        """)

    def install(self, binary_path: str, config_path: str, user: bool) -> None:
        unit_path = self._unit_path(user)

        if unit_path.exists():
            print(
                f"Error: Service already installed at {unit_path}. "
                "Remove it first with 'hass-companion service uninstall'.",
                file=sys.stderr,
            )
            sys.exit(1)

        if not user and os.geteuid() != 0:
            print(
                "Error: System-level install requires root. "
                "Use --user for user-level, or run with sudo.",
                file=sys.stderr,
            )
            sys.exit(1)

        unit_content = self._generate_unit(binary_path, config_path, user)
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(unit_content)

        daemon_reload_cmd = ["systemctl"]
        if user:
            daemon_reload_cmd.append("--user")
        daemon_reload_cmd.append("daemon-reload")
        subprocess.run(daemon_reload_cmd, check=True)

        scope = "--user " if user else ""
        print(f"Service installed: {unit_path}")
        print(f"  Enable: systemctl {scope}enable {SERVICE_NAME}")
        print(f"  Start:  systemctl {scope}start {SERVICE_NAME}")

    def uninstall(self, user: bool) -> None:
        unit_path = self._unit_path(user)

        if not unit_path.exists():
            print("Service not installed.", file=sys.stderr)
            sys.exit(1)

        if not user and os.geteuid() != 0:
            print(
                "Error: System-level uninstall requires root. "
                "Use --user for user-level, or run with sudo.",
                file=sys.stderr,
            )
            sys.exit(1)

        scope_args = ["--user"] if user else []

        # Stop if running
        subprocess.run(
            ["systemctl", *scope_args, "stop", SERVICE_NAME],
            capture_output=True,
        )
        # Disable
        subprocess.run(
            ["systemctl", *scope_args, "disable", SERVICE_NAME],
            capture_output=True,
        )
        # Remove unit file
        unit_path.unlink()
        # Reload daemon
        subprocess.run(["systemctl", *scope_args, "daemon-reload"], check=True)

        print(f"Service uninstalled (removed {unit_path}).")

    def status(self) -> ServiceStatus:
        # Check both user and system paths
        for user in (True, False):
            unit_path = self._unit_path(user)
            if unit_path.exists():
                scope_args = ["--user"] if user else []
                enabled = (
                    subprocess.run(
                        ["systemctl", *scope_args, "is-enabled", SERVICE_NAME],
                        capture_output=True,
                        text=True,
                    ).returncode
                    == 0
                )
                active = (
                    subprocess.run(
                        ["systemctl", *scope_args, "is-active", SERVICE_NAME],
                        capture_output=True,
                        text=True,
                    ).returncode
                    == 0
                )
                return ServiceStatus(
                    installed=True,
                    enabled=enabled,
                    running=active,
                    unit_path=unit_path,
                )

        return ServiceStatus(installed=False, enabled=False, running=False)



class LaunchdBackend(PlatformBackend):
    """macOS launchd service backend."""

    PLIST_DIR = Path.home() / "Library/LaunchAgents"

    def _plist_path(self) -> Path:
        return self.PLIST_DIR / f"{LAUNCHD_LABEL}.plist"

    def _generate_plist(self, binary_path: str, config_path: str) -> str:
        log_path = "/usr/local/var/log/hass-companion.log"
        return textwrap.dedent(f"""\
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
              "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>Label</key>
                <string>{LAUNCHD_LABEL}</string>
                <key>ProgramArguments</key>
                <array>
                    <string>{binary_path}</string>
                    <string>--config</string>
                    <string>{config_path}</string>
                </array>
                <key>RunAtLoad</key>
                <true/>
                <key>KeepAlive</key>
                <true/>
                <key>StandardOutPath</key>
                <string>{log_path}</string>
                <key>StandardErrorPath</key>
                <string>{log_path}</string>
            </dict>
            </plist>
        """)

    def install(self, binary_path: str, config_path: str, user: bool) -> None:
        plist_path = self._plist_path()

        if plist_path.exists():
            print(
                f"Error: Service already installed at {plist_path}. "
                "Remove it first with 'hass-companion service uninstall'.",
                file=sys.stderr,
            )
            sys.exit(1)

        plist_content = self._generate_plist(binary_path, config_path)
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(plist_content)

        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print(f"Service installed and loaded: {plist_path}")

    def uninstall(self, user: bool) -> None:
        plist_path = self._plist_path()

        if not plist_path.exists():
            print("Service not installed.", file=sys.stderr)
            sys.exit(1)

        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
        )
        plist_path.unlink()
        print(f"Service uninstalled (removed {plist_path}).")

    def status(self) -> ServiceStatus:
        plist_path = self._plist_path()

        if not plist_path.exists():
            return ServiceStatus(installed=False, enabled=False, running=False)

        # Check if loaded via launchctl list
        result = subprocess.run(
            ["launchctl", "list", LAUNCHD_LABEL],
            capture_output=True,
            text=True,
        )
        running = result.returncode == 0

        return ServiceStatus(
            installed=True,
            enabled=True,  # launchd plist in LaunchAgents is always "enabled"
            running=running,
            unit_path=plist_path,
        )


def _detect_binary_path() -> str:
    """Detect the path to the hass-companion binary."""
    # Check if running as an installed entry point
    binary = shutil.which("hass-companion")
    if binary:
        return binary

    # Fallback: use the current Python interpreter + module
    return f"{sys.executable} -m hass_companion"


def _is_nixos() -> bool:
    """Detect if running on NixOS."""
    if Path("/etc/NIXOS").exists():
        return True
    if "NIX_PATH" in os.environ:
        return True
    return False


class ServiceManager:
    """Dispatches service operations to the appropriate platform backend."""

    def get_backend(self) -> PlatformBackend:
        """Detect platform and return the appropriate backend."""
        if _is_nixos():
            print(
                "Error: On NixOS, use the declarative NixOS module instead.\n"
                "See README for instructions on enabling services.hass-companion.",
                file=sys.stderr,
            )
            sys.exit(1)

        if sys.platform == "linux":
            return SystemdBackend()
        elif sys.platform == "darwin":
            return LaunchdBackend()
        else:
            print(
                "Error: Service installation not supported on this platform. "
                "Supported: Linux (systemd), macOS (launchd).",
                file=sys.stderr,
            )
            sys.exit(1)

    def install(self, config_path: str, user: bool = False) -> None:
        """Install the service."""
        backend = self.get_backend()
        binary_path = _detect_binary_path()
        if not binary_path:
            print(
                "Error: Could not determine hass-companion binary path. "
                "Ensure it's installed via pip/pipx.",
                file=sys.stderr,
            )
            sys.exit(1)
        backend.install(binary_path, config_path, user)

    def uninstall(self, user: bool = False) -> None:
        """Uninstall the service."""
        backend = self.get_backend()
        backend.uninstall(user)

    def status(self) -> ServiceStatus:
        """Get service status."""
        backend = self.get_backend()
        return backend.status()
