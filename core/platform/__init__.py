"""Platform abstraction layer — detects OS and exports a singleton.

Usage:
    from core.platform import current_platform
    cmd = current_platform.build_ping_command("8.8.8.8", timeout=5.0)
"""

import platform as _platform

from core.platform.base import PlatformCommands
from core.platform.linux import LinuxPlatform
from core.platform.darwin import DarwinPlatform

_PLATFORMS: dict[str, type[PlatformCommands]] = {
    "Linux": LinuxPlatform,
    "Darwin": DarwinPlatform,
}


def get_platform() -> PlatformCommands:
    """Detect the current OS and return the appropriate platform implementation.

    Raises RuntimeError on unsupported platforms.
    """
    system = _platform.system()
    cls = _PLATFORMS.get(system)
    if cls is None:
        raise RuntimeError(f"Unsupported platform: {system}. Supported: {list(_PLATFORMS.keys())}")
    return cls()


current_platform: PlatformCommands = get_platform()
