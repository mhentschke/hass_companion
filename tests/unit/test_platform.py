"""Unit tests for core.platform abstraction layer."""

from unittest.mock import patch

import pytest

from core.platform import get_platform
from core.platform.darwin import DarwinPlatform
from core.platform.linux import LinuxPlatform


class TestLinuxPlatform:
    def test_build_ping_command_basic(self):
        p = LinuxPlatform()
        cmd = p.build_ping_command("8.8.8.8")
        assert cmd == ["ping", "-c", "1", "-W", "5", "8.8.8.8"]

    def test_build_ping_command_with_timeout(self):
        p = LinuxPlatform()
        cmd = p.build_ping_command("8.8.8.8", timeout=10.0)
        assert cmd == ["ping", "-c", "1", "-W", "10", "8.8.8.8"]

    def test_build_ping_command_with_interface_and_size(self):
        p = LinuxPlatform()
        cmd = p.build_ping_command("8.8.8.8", interface="eth0", size=64)
        assert cmd == ["ping", "-c", "1", "-W", "5", "-I", "eth0", "-s", "64", "8.8.8.8"]

    def test_build_dns_command(self):
        p = LinuxPlatform()
        assert p.build_dns_command("google.com") == ["dig", "google.com"]

    def test_default_shell(self):
        p = LinuxPlatform()
        assert p.default_shell == "/bin/bash"

    def test_default_network_excludes(self):
        p = LinuxPlatform()
        assert r"^veth" in p.default_network_excludes
        assert r"^lo$" in p.default_network_excludes

    def test_default_disk_includes(self):
        p = LinuxPlatform()
        assert r"^/dev/" in p.default_disk_includes


class TestDarwinPlatform:
    def test_build_ping_command_uses_milliseconds(self):
        p = DarwinPlatform()
        cmd = p.build_ping_command("8.8.8.8", timeout=5.0)
        # macOS -W takes milliseconds: 5.0s -> 5000ms
        assert cmd == ["ping", "-c", "1", "-W", "5000", "8.8.8.8"]

    def test_build_ping_command_with_interface_and_size(self):
        p = DarwinPlatform()
        cmd = p.build_ping_command("8.8.8.8", timeout=2.0, interface="en0", size=128)
        assert cmd == ["ping", "-c", "1", "-W", "2000", "-I", "en0", "-s", "128", "8.8.8.8"]

    def test_build_dns_command(self):
        p = DarwinPlatform()
        assert p.build_dns_command("google.com") == ["dig", "google.com"]

    def test_default_shell(self):
        p = DarwinPlatform()
        assert p.default_shell == "/bin/bash"

    def test_default_network_excludes(self):
        p = DarwinPlatform()
        assert r"^utun" in p.default_network_excludes
        assert r"^awdl" in p.default_network_excludes
        assert r"^lo0$" in p.default_network_excludes

    def test_default_disk_includes(self):
        p = DarwinPlatform()
        assert r"^/dev/disk" in p.default_disk_includes


class TestGetPlatform:
    def test_returns_linux_on_linux(self):
        with patch("core.platform._platform.system", return_value="Linux"):
            p = get_platform()
            assert isinstance(p, LinuxPlatform)

    def test_returns_darwin_on_macos(self):
        with patch("core.platform._platform.system", return_value="Darwin"):
            p = get_platform()
            assert isinstance(p, DarwinPlatform)

    def test_raises_on_unsupported_os(self):
        with patch("core.platform._platform.system", return_value="Windows"):
            with pytest.raises(RuntimeError, match="Unsupported platform: Windows"):
                get_platform()
