"""Smoke tests — verify app lifecycle against a real MQTT broker.

These tests require Docker to be running and use the mqtt_broker fixture
from conftest.py to spin up a Mosquitto container.
"""

import json
import os
import signal
import subprocess
import time

import pytest

pytestmark = pytest.mark.smoke

SMOKE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SMOKE_DIR, "..", ".."))
APP_SCRIPT = os.path.join(PROJECT_ROOT, "hass-companion.py")
PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python")

# MQTT topic patterns for the echo_sensor entity
DISCOVERY_TOPIC_PATTERN = "homeassistant/#"


def _start_app(port: int) -> subprocess.Popen:
    """Start the hass-companion app as a subprocess."""
    env = os.environ.copy()
    env["TEST_MQTT_PORT"] = str(port)
    env["LOG_LEVEL"] = "DEBUG"
    # Clear any existing MQTT env vars that might interfere
    env.pop("HA_MQTT_HOST", None)
    env.pop("HA_MQTT_PORT", None)
    env.pop("HA_MQTT_USERNAME", None)
    env.pop("HA_MQTT_PASSWORD", None)

    proc = subprocess.Popen(
        [PYTHON, APP_SCRIPT],
        env=env,
        cwd=SMOKE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def _connect_mqtt_client(port: int):
    """Create and connect a paho MQTT client."""
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("localhost", port)
    client.loop_start()
    return client


def test_app_publishes_discovery(mqtt_broker):
    """App starts and publishes an MQTT discovery message for the sensor."""
    port = mqtt_broker
    client = _connect_mqtt_client(port)

    try:
        # Subscribe to discovery topic before starting app
        messages = []

        def on_message(_client, _userdata, msg):
            messages.append(msg)

        client.subscribe("homeassistant/#")
        client.on_message = on_message

        # Start the app
        proc = _start_app(port)
        try:
            # Wait for discovery message
            deadline = time.time() + 15.0
            discovery_found = False
            while time.time() < deadline and not discovery_found:
                time.sleep(0.5)
                for msg in messages:
                    if "/config" in msg.topic and "sensor" in msg.topic.lower():
                        discovery_found = True
                        # Verify it's valid JSON with expected fields
                        payload = json.loads(msg.payload.decode())
                        assert "name" in payload
                        break

            assert discovery_found, (
                f"No discovery message for echo_sensor within 15s. "
                f"Got {len(messages)} messages on topics: {[m.topic for m in messages]}"
            )
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
    finally:
        client.loop_stop()
        client.disconnect()


def test_sensor_state_arrives(mqtt_broker):
    """Sensor state '42' arrives on the state topic within a reasonable time."""
    port = mqtt_broker
    client = _connect_mqtt_client(port)

    try:
        messages = []

        def on_message(_client, _userdata, msg):
            messages.append(msg)

        # Subscribe to all topics to catch state messages wherever they land
        client.subscribe("#")
        client.on_message = on_message

        proc = _start_app(port)
        try:
            # Wait for a state message containing "42"
            deadline = time.time() + 15.0
            state_found = False
            while time.time() < deadline and not state_found:
                time.sleep(0.5)
                for msg in messages:
                    if "/config" not in msg.topic:
                        payload = msg.payload.decode()
                        if "42" in payload:
                            state_found = True
                            break

            assert state_found, (
                f"No state message with '42' within 15s. "
                f"Got {len(messages)} messages on topics: {[m.topic for m in messages]}"
            )
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=10)
    finally:
        client.loop_stop()
        client.disconnect()


def test_app_shuts_down_cleanly_on_sigterm(mqtt_broker):
    """App exits cleanly (exit code 0) when receiving SIGTERM."""
    port = mqtt_broker

    proc = _start_app(port)
    # Give the app time to start
    time.sleep(3)

    # Send SIGTERM
    proc.send_signal(signal.SIGTERM)

    # Wait for exit
    try:
        returncode = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("App did not exit within 10s after SIGTERM")

    assert returncode == 0, (
        f"App exited with code {returncode}. "
        f"stderr: {proc.stderr.read().decode()}"
    )
