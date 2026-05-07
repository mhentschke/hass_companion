"""Comprehensive smoke tests — verify all entity types against a real MQTT broker.

Tests exercise:
- Command sensor with parser pipeline (regex + int)
- Binary sensor with bool parser
- Switch with command_on/command_off and binary_sensor feedback
- Button press command
- Select with command_template, state_map, and sensor feedback
- System entities (cpu, memory, disk)
- Graceful shutdown via SIGTERM

Requires Docker to be running. Uses the mqtt_broker fixture from conftest.py.
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


def _start_app(port: int) -> subprocess.Popen:
    """Start the hass-companion app as a subprocess with the smoke config."""
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


def _stop_app(proc: subprocess.Popen) -> None:
    """Stop the app gracefully, kill if it doesn't respond."""
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _connect_mqtt_client(port: int):
    """Create and connect a paho MQTT client."""
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect("localhost", port)
    client.loop_start()
    return client


def _collect_messages(client):
    """Subscribe to all topics and return the shared message list."""
    messages = []

    def on_message(_client, _userdata, msg):
        messages.append(msg)

    client.on_message = on_message
    client.subscribe("#")
    # Brief pause to ensure subscription is established before app starts
    time.sleep(0.5)
    return messages


def _wait_for_message(messages, predicate, timeout: float = 15.0):
    """Wait until a message matching predicate appears in the list."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for msg in messages:
            if predicate(msg):
                return msg
        time.sleep(0.3)
    return None


def _is_numeric(s: str) -> bool:
    """Check if a string represents a numeric value."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


class TestDiscovery:
    """Verify MQTT discovery messages arrive for all entity types."""

    def test_sensor_discovery(self, mqtt_broker):
        """Command sensor publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Echo-Sensor" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Echo-Sensor. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_binary_sensor_discovery(self, mqtt_broker):
        """Binary sensor publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Echo-Binary" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Echo-Binary. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_switch_discovery(self, mqtt_broker):
        """Switch publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "File-Switch" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for File-Switch. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_button_discovery(self, mqtt_broker):
        """Button publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Echo-Button" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Echo-Button. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload

            # Button is created — verify app is still running (no crash)
            assert proc.poll() is None, "App crashed during entity creation"
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_select_discovery(self, mqtt_broker):
        """Select publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Mode-Select" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Mode-Select. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_system_entity_discovery(self, mqtt_broker):
        """System entities (cpu) publish discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "CPU" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for system CPU entity. Topics: {[m.topic for m in messages if '/config' in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestStateUpdates:
    """Verify state updates arrive for polling entities."""

    def test_command_sensor_state(self, mqtt_broker):
        """Command sensor publishes parsed state '42'."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" not in m.topic and "Echo-Sensor" in m.topic and m.payload.decode() == "42",
            )
            assert msg is not None, (
                f"No state '42' for Echo-Sensor. "
                f"Non-config messages: {[(m.topic, m.payload.decode()) for m in messages if '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_binary_sensor_state(self, mqtt_broker):
        """Binary sensor publishes state (ON or true)."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: (
                    "/config" not in m.topic
                    and "Echo-Binary" in m.topic
                    and m.payload.decode().upper() in ("ON", "TRUE", "1")
                ),
            )
            assert msg is not None, (
                f"No ON/true state for Echo-Binary. "
                f"Binary messages: {[(m.topic, m.payload.decode()) for m in messages if 'Echo-Binary' in m.topic and '/config' not in m.topic]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_system_sensor_state(self, mqtt_broker):
        """System CPU sensor publishes a numeric state."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" not in m.topic and "CPU" in m.topic and _is_numeric(m.payload.decode()),
            )
            assert msg is not None, (
                f"No numeric state for CPU entity. "
                f"Non-config messages: {[(m.topic, m.payload.decode()) for m in messages if '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestNetworkIOEntities:
    """Verify network IO entities publish discovery and state updates."""

    def test_network_io_discovery(self, mqtt_broker):
        """Network IO entity publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Network-IO" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Network IO entity. "
                f"Config topics: {[m.topic for m in messages if '/config' in m.topic][:30]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_network_io_state(self, mqtt_broker):
        """Network IO entity publishes numeric state updates."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" not in m.topic and "Network-IO" in m.topic and _is_numeric(m.payload.decode()),
            )
            assert msg is not None, (
                f"No numeric state for Network IO entity. "
                f"Network messages: {[(m.topic, m.payload.decode()) for m in messages if 'Network' in m.topic and '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestPingSensorEntities:
    """Verify ping sensor entities publish discovery and state updates."""

    def test_ping_sensor_discovery(self, mqtt_broker):
        """Ping sensor publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "ping" in m.topic.lower(),
            )
            assert msg is not None, (
                f"No discovery for Ping sensor. "
                f"Config topics: {[m.topic for m in messages if '/config' in m.topic][:30]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_ping_sensor_state(self, mqtt_broker):
        """Ping sensor publishes numeric RTT state."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" not in m.topic and "ping" in m.topic.lower() and _is_numeric(m.payload.decode()),
            )
            assert msg is not None, (
                f"No numeric state for Ping sensor. "
                f"Ping messages: {[(m.topic, m.payload.decode()) for m in messages if 'ping' in m.topic.lower() and '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestDNSSensorEntities:
    """Verify DNS sensor entities publish discovery and state updates."""

    def test_dns_sensor_discovery(self, mqtt_broker):
        """DNS sensor publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "dns" in m.topic.lower(),
            )
            assert msg is not None, (
                f"No discovery for DNS sensor. "
                f"Config topics: {[m.topic for m in messages if '/config' in m.topic][:30]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_dns_sensor_state(self, mqtt_broker):
        """DNS sensor publishes numeric resolution time state."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" not in m.topic and "dns" in m.topic.lower() and _is_numeric(m.payload.decode()),
            )
            assert msg is not None, (
                f"No numeric state for DNS sensor. "
                f"DNS messages: {[(m.topic, m.payload.decode()) for m in messages if 'dns' in m.topic.lower() and '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestProcessEntities:
    """Verify process monitoring entities publish discovery and state updates."""

    def test_process_sensor_discovery(self, mqtt_broker):
        """Process sensor publishes discovery config."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Process" in m.topic,
            )
            assert msg is not None, (
                f"No discovery for Process sensor. "
                f"Config topics: {[m.topic for m in messages if '/config' in m.topic][:30]}"
            )
            payload = json.loads(msg.payload.decode())
            assert "name" in payload
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_process_sensor_state(self, mqtt_broker):
        """Process sensor publishes state updates (status or numeric)."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            # Process entity publishes multiple sensors — look for any state update
            # that contains a process-related value (numeric or status string)
            msg = _wait_for_message(
                messages,
                lambda m: (
                    "/config" not in m.topic
                    and "Process" in m.topic
                    and (
                        _is_numeric(m.payload.decode()) or m.payload.decode() in ("running", "sleeping", "Not Running")
                    )
                ),
            )
            assert msg is not None, (
                f"No state for Process sensor. "
                f"Process messages: {[(m.topic, m.payload.decode()) for m in messages if 'Process' in m.topic and '/config' not in m.topic][:20]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestInteractiveCommands:
    """Verify interactive entities respond to MQTT commands."""

    def test_switch_on_off(self, mqtt_broker):
        """Publishing ON to switch command topic results in state feedback."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            # Wait for switch discovery to get the command topic
            discovery_msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "File-Switch" in m.topic,
            )
            assert discovery_msg is not None, "Switch discovery not received"

            payload = json.loads(discovery_msg.payload.decode())
            command_topic = payload.get("command_topic", payload.get("cmd_t"))
            assert command_topic, f"No command_topic in discovery: {payload.keys()}"

            # Send ON command
            client.publish(command_topic, "ON")

            # Wait for state feedback showing ON
            msg = _wait_for_message(
                messages,
                lambda m: (
                    "/config" not in m.topic
                    and "File-Switch" in m.topic
                    and m.payload.decode().upper() in ("ON", "TRUE", "1")
                ),
                timeout=10.0,
            )
            assert msg is not None, (
                f"No ON state for File-Switch after command. "
                f"Switch messages: {[(m.topic, m.payload.decode()) for m in messages if 'File-Switch' in m.topic and '/config' not in m.topic]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_button_press(self, mqtt_broker):
        """Publishing press to button command topic does not crash the app."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            # Wait for button discovery to get the command topic
            discovery_msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Echo-Button" in m.topic,
            )
            assert discovery_msg is not None, "Button discovery not received"

            payload = json.loads(discovery_msg.payload.decode())
            command_topic = payload.get("command_topic", payload.get("cmd_t"))
            assert command_topic, f"No command_topic in discovery: {payload.keys()}"

            # Send press command
            client.publish(command_topic, "PRESS")

            # Give the app time to process — it should not crash
            time.sleep(3)
            assert proc.poll() is None, (
                f"App crashed after button press. Return code: {proc.returncode}, stderr: {proc.stderr.read().decode()}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()

    def test_select_command(self, mqtt_broker):
        """Publishing selection to select command topic results in state update."""
        port = mqtt_broker
        client = _connect_mqtt_client(port)
        messages = _collect_messages(client)

        proc = _start_app(port)
        try:
            # Wait for select discovery to get the command topic
            discovery_msg = _wait_for_message(
                messages,
                lambda m: "/config" in m.topic and "Mode-Select" in m.topic,
            )
            assert discovery_msg is not None, "Select discovery not received"

            payload = json.loads(discovery_msg.payload.decode())
            command_topic = payload.get("command_topic", payload.get("cmd_t"))
            assert command_topic, f"No command_topic in discovery: {payload.keys()}"

            # Send selection command (use a display name from state_map)
            client.publish(command_topic, "High")

            # Wait for state update reflecting the selection
            msg = _wait_for_message(
                messages,
                lambda m: (
                    "/config" not in m.topic and "Mode-Select" in m.topic and m.payload.decode() in ("High", "high")
                ),
                timeout=10.0,
            )
            assert msg is not None, (
                f"No state update for Mode-Select after command. "
                f"Select messages: {[(m.topic, m.payload.decode()) for m in messages if 'Mode-Select' in m.topic and '/config' not in m.topic]}"
            )
        finally:
            _stop_app(proc)
            client.loop_stop()
            client.disconnect()


class TestGracefulShutdown:
    """Verify the app shuts down cleanly on SIGTERM."""

    def test_sigterm_clean_exit(self, mqtt_broker):
        """App exits with code 0 on SIGTERM."""
        port = mqtt_broker
        proc = _start_app(port)

        # Give the app time to start and initialize entities
        time.sleep(5)

        # Verify app is still running
        assert proc.poll() is None, (
            f"App exited prematurely. Code: {proc.returncode}, stderr: {proc.stderr.read().decode()}"
        )

        # Send SIGTERM
        proc.send_signal(signal.SIGTERM)

        try:
            returncode = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            pytest.fail("App did not exit within 15s after SIGTERM")

        assert returncode == 0, f"App exited with code {returncode}. stderr: {proc.stderr.read().decode()}"
