"""Reusable include/exclude filter with regex pattern matching.

Used by system entities to filter disks, NICs, and other enumerable resources.
Provides smart defaults for common platforms (NixOS bind mounts, virtual NICs).
"""

import re
from typing import Sequence


class EntityFilter:
    """Include/exclude filter using regex patterns.

    Rules:
    - If include is non-empty: only items matching at least one include pattern pass.
    - If exclude is non-empty: items matching any exclude pattern are rejected.
    - Include is evaluated first (whitelist), then exclude (blacklist).
    - If both are empty: everything passes.
    """

    def __init__(
        self,
        include: Sequence[str] | None = None,
        exclude: Sequence[str] | None = None,
    ):
        self._include = [re.compile(p) for p in (include or [])]
        self._exclude = [re.compile(p) for p in (exclude or [])]

    def matches(self, value: str) -> bool:
        """Returns True if value passes the filter."""
        # Include check: if patterns defined, value must match at least one
        if self._include:
            if not any(p.search(value) for p in self._include):
                return False
        # Exclude check: if value matches any exclude pattern, reject
        if self._exclude:
            if any(p.search(value) for p in self._exclude):
                return False
        return True

    def filter_list(self, items: Sequence[str]) -> list[str]:
        """Filter a list of strings, returning only those that pass."""
        return [item for item in items if self.matches(item)]

    def filter_dict(self, d: dict) -> dict:
        """Filter a dict by keys, returning only entries whose key passes."""
        return {k: v for k, v in d.items() if self.matches(k)}

    @property
    def is_empty(self) -> bool:
        """True if no include or exclude patterns are defined."""
        return not self._include and not self._exclude


# --- Smart defaults ---

def default_disk_usage_filter() -> EntityFilter:
    """Skip virtual filesystems, NixOS bind mounts, and snap mounts.

    Designed to keep only meaningful, distinct mount points:
    - Real block devices (/dev/*)
    - Excludes /nix/store sub-mounts and common NixOS bind-mount noise
    - Excludes /snap/ mounts

    For NixOS systems with many bind mounts from the same partition,
    use explicit include filters in config to select specific mountpoints.
    """
    return EntityFilter(
        include=[r"^/dev/"],
        exclude=[
            r"/nix/store",
            r"/snap/",
        ],
    )


def default_network_filter() -> EntityFilter:
    """Skip virtual/container network interfaces.

    Keeps physical NICs and common real interfaces.
    """
    return EntityFilter(exclude=[
        r"^veth",
        r"^docker",
        r"^br-",
        r"^virbr",
        r"^vnet",
        r"^lo$",
        r"^macvtap",
    ])
