#!/usr/bin/env python3
"""Thin shim for backward compatibility. Use `hass-companion` CLI instead."""

from hass_companion.cli import main

if __name__ == "__main__":
    main()
