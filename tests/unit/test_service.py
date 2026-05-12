"""Unit tests for service template generation and platform detection."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hass_companion.service import (
    LaunchdBackend,
    ServiceManager,
    SystemdBackend,
    _detect_binary_path,
    _is_nixos,
)


class TestSystemdTemplateGeneration:
    """Test systemd unit file generation."""

    def test_system_level_unit(self):
        backend = SystemdBackend()
        unit = backend._generate_unit("/usr/bin/hass-companion", "/etc/hass/config.yaml", user=False)
        assert "ExecStart=/usr/bin/hass-companion --config /etc/hass/config.yaml" in unit
        assert "WantedBy=multi-user.target" in unit
        assert "Restart=on-failure" in unit
        assert "After=network-online.target" in unit

    def test_user_level_unit(self):
        backend = SystemdBackend()
        unit = backend._generate_unit("/home/user/.local/bin/hass-companion", "~/config.yaml", user=True)
        assert "ExecStart=/home/user/.local/bin/hass-companion --config ~/config.yaml" in unit
        assert "WantedBy=default.target" in unit

    def test_unit_path_system(self):
        backend = SystemdBackend()
        path = backend._unit_path(user=False)
        assert path == Path("/etc/systemd/system/hass-companion.service")

    def test_unit_path_user(self):
        backend = SystemdBackend()
        path = backend._unit_path(user=True)
        assert path == Path.home() / ".config/systemd/user/hass-companion.service"

    def test_config_path_with_spaces(self):
        backend = SystemdBackend()
        unit = backend._generate_unit("/usr/bin/hass-companion", "/path/with spaces/config.yaml", user=False)
        assert "--config /path/with spaces/config.yaml" in unit


class TestLaunchdTemplateGeneration:
    """Test launchd plist generation."""

    def test_plist_content(self):
        backend = LaunchdBackend()
        plist = backend._generate_plist("/usr/local/bin/hass-companion", "/Users/me/config.yaml")
        assert "<string>com.hass-companion</string>" in plist
        assert "<string>/usr/local/bin/hass-companion</string>" in plist
        assert "<string>/Users/me/config.yaml</string>" in plist
        assert "<key>RunAtLoad</key>" in plist
        assert "<key>KeepAlive</key>" in plist

    def test_plist_path(self):
        backend = LaunchdBackend()
        path = backend._plist_path()
        assert path == Path.home() / "Library/LaunchAgents/com.hass-companion.plist"

    def test_plist_with_different_config(self):
        backend = LaunchdBackend()
        plist = backend._generate_plist("/opt/bin/hass-companion", "/opt/hass/config.yaml")
        assert "<string>/opt/bin/hass-companion</string>" in plist
        assert "<string>/opt/hass/config.yaml</string>" in plist


class TestPlatformDetection:
    """Test platform detection logic."""

    @patch("hass_companion.service.Path.exists", return_value=True)
    def test_nixos_detected_via_etc_file(self, mock_exists):
        assert _is_nixos() is True

    @patch("hass_companion.service.Path.exists", return_value=False)
    @patch.dict("os.environ", {"NIX_PATH": "/nix/var/nix/profiles"})
    def test_nixos_detected_via_env(self, mock_exists):
        assert _is_nixos() is True

    @patch("hass_companion.service.Path.exists", return_value=False)
    @patch.dict("os.environ", {}, clear=True)
    def test_not_nixos(self, mock_exists):
        assert _is_nixos() is False

    @patch("hass_companion.service._is_nixos", return_value=True)
    def test_service_manager_blocks_on_nixos(self, mock_nix, capsys):
        manager = ServiceManager()
        with pytest.raises(SystemExit) as exc_info:
            manager.get_backend()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "NixOS" in captured.err
        assert "declarative NixOS module" in captured.err

    @patch("hass_companion.service._is_nixos", return_value=False)
    @patch("sys.platform", "linux")
    def test_linux_returns_systemd_backend(self, mock_nix):
        manager = ServiceManager()
        backend = manager.get_backend()
        assert isinstance(backend, SystemdBackend)

    @patch("hass_companion.service._is_nixos", return_value=False)
    @patch("sys.platform", "darwin")
    def test_darwin_returns_launchd_backend(self, mock_nix):
        manager = ServiceManager()
        backend = manager.get_backend()
        assert isinstance(backend, LaunchdBackend)

    @patch("hass_companion.service._is_nixos", return_value=False)
    @patch("sys.platform", "win32")
    def test_unsupported_platform_exits(self, mock_nix, capsys):
        manager = ServiceManager()
        with pytest.raises(SystemExit) as exc_info:
            manager.get_backend()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "not supported" in captured.err
