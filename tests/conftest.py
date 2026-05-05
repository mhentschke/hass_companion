"""Shared test fixtures for hass-companion."""

import pytest


@pytest.fixture
def sample_mqtt_settings() -> dict:
    """Minimal MQTT settings for testing."""
    return {
        "host": "localhost",
        "port": 1883,
        "username": None,
        "password": None,
    }


@pytest.fixture
def sample_hass_settings() -> dict:
    """Minimal Home Assistant device settings."""
    return {
        "device_name": "Test Device",
        "device_id": "test_device",
    }
