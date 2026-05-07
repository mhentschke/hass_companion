"""Unit tests for CLI argument parsing and modes."""

import subprocess
import sys

import pytest

from hass_companion import __version__
from hass_companion.cli import build_parser


class TestCLIArgParsing:
    """Test argparse configuration."""

    def test_version_flag(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in captured.out

    def test_config_default(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.config == "config.yaml"

    def test_config_override(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "/tmp/custom.yaml"])
        assert args.config == "/tmp/custom.yaml"

    def test_validate_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--validate"])
        assert args.validate is True

    def test_dry_run_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_log_level_default(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.log_level == "INFO"

    def test_log_level_override(self):
        parser = build_parser()
        args = parser.parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_invalid_log_level_rejected(self, capsys):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--log-level", "INVALID"])
        assert exc_info.value.code == 2


class TestCLIValidateMode:
    """Test --validate via subprocess to verify exit codes."""

    def test_validate_valid_config(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("mqtt:\n  host: localhost\n  port: 1883\nhass:\n  device_name: Test\n  device_id: test\n")
        result = subprocess.run(
            [sys.executable, "-m", "hass_companion", "--validate", "--config", str(config)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Configuration valid" in result.stdout

    def test_validate_invalid_config(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text("mqtt:\n  port: abc\n")
        result = subprocess.run(
            [sys.executable, "-m", "hass_companion", "--validate", "--config", str(config)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_validate_missing_config(self):
        result = subprocess.run(
            [sys.executable, "-m", "hass_companion", "--validate", "--config", "/nonexistent.yaml"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr


class TestCLIDryRunMode:
    """Test --dry-run via subprocess."""

    def test_dry_run_valid_config(self, tmp_path):
        config = tmp_path / "config.yaml"
        config.write_text(
            "mqtt:\n  host: localhost\n  port: 1883\n"
            "hass:\n  device_name: Test\n  device_id: test\n"
            "entities:\n  sensors:\n    - name: Echo\n      command: echo 1\n"
        )
        result = subprocess.run(
            [sys.executable, "-m", "hass_companion", "--dry-run", "--config", str(config)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "[sensor] Echo" in result.stdout
        assert "No MQTT connection was made" in result.stdout
