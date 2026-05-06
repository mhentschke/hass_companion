"""Smoke test fixtures — Docker Mosquitto broker management."""

import os
import subprocess
import time

import pytest

COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "docker-compose.yml")
SERVICE_NAME = "mosquitto"


def _get_broker_port() -> int:
    """Get the mapped host port for the Mosquitto broker."""
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "port", SERVICE_NAME, "1883"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get broker port: {result.stderr}")
    # Output is like "0.0.0.0:32768"
    return int(result.stdout.strip().split(":")[-1])


def _wait_for_broker(port: int, timeout: float = 15.0) -> None:
    """Wait until the MQTT broker accepts connections."""
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            sock = socket.create_connection(("localhost", port), timeout=1)
            sock.close()
            return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    raise TimeoutError(f"Broker on port {port} not ready within {timeout}s")


@pytest.fixture(scope="session")
def mqtt_broker():
    """Start Docker Mosquitto broker for the test session.

    Yields the broker port. Tears down the container after tests complete.
    """
    # Start the broker
    subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "-d", "--wait"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    try:
        port = _get_broker_port()
        _wait_for_broker(port)
        # Set env var so test config can resolve it
        os.environ["TEST_MQTT_PORT"] = str(port)
        yield port
    finally:
        subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "down", "-v"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        os.environ.pop("TEST_MQTT_PORT", None)
