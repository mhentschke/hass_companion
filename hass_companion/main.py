"""Main application logic for hass-companion."""

import asyncio
import logging
import signal
import sys

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from ha_mqtt_discoverable import DeviceInfo as HADeviceInfo
from ha_mqtt_discoverable import Settings as HASettings

from core.config import ConfigError, load_config
from core.discovery import clean_discovery
from core.entities.base import BaseEntity
from core.entities.system import create_system_entities
from core.factory import create_entity as factory_create_entity
from core.logging import setup_logging  # noqa: F401 — re-exported for CLI
from core.mqtt import MQTTReconnectionManager

logger = logging.getLogger(__name__)


def validate_config(config_path: str) -> int:
    """Validate configuration file and return exit code."""
    load_dotenv()
    try:
        load_config(config_path)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("Configuration valid")
    return 0


def dry_run(config_path: str) -> int:
    """Report what entities would be created without connecting to MQTT."""
    load_dotenv()

    try:
        app_config = load_config(config_path)
    except ConfigError as e:
        print(str(e), file=sys.stderr)
        return 1

    ha_device_name = app_config.hass.device_name

    print("Dry-run mode — entities that would be created:")
    print("-" * 60)

    count = 0

    entity_types = [
        ("sensor", app_config.entities.sensors),
        ("binary_sensor", app_config.entities.binary_sensors),
        ("switch", app_config.entities.switches),
        ("button", app_config.entities.buttons),
        ("select", app_config.entities.selects),
    ]

    for entity_type, configs in entity_types:
        for config in configs:
            device_key = getattr(config, "device", None)
            device_name = app_config.devices[device_key].name if device_key else ha_device_name
            name = getattr(config, "name", "unnamed")
            print(f"  [{entity_type}] {name} (device: {device_name})")
            count += 1

    if app_config.entities.system:
        sys_config = app_config.entities.system
        if sys_config.cpu:
            if sys_config.cpu.percent:
                print(f"  [system] CPU Percent (device: {ha_device_name})")
                count += 1
            if sys_config.cpu.freq:
                print(f"  [system] CPU Frequency (device: {ha_device_name})")
                count += 1
        if sys_config.memory:
            if sys_config.memory.virtual is not None:
                print(f"  [system] Memory Virtual (device: {ha_device_name})")
                count += 1
            if sys_config.memory.swap is not None:
                print(f"  [system] Memory Swap (device: {ha_device_name})")
                count += 1
        if sys_config.storage:
            if sys_config.storage.usage:
                print(f"  [system] Disk Usage (device: {ha_device_name})")
                count += 1
            if sys_config.storage.io:
                print(f"  [system] Disk IO (device: {ha_device_name})")
                count += 1
        if sys_config.network:
            if sys_config.network.io:
                print(f"  [system] Network IO (device: {ha_device_name})")
                count += 1
            for ping in sys_config.network.ping:
                print(f"  [system] Ping {ping.host} (device: {ha_device_name})")
                count += 1
            for dns in sys_config.network.dns:
                print(f"  [system] DNS {dns.host} (device: {ha_device_name})")
                count += 1
        if sys_config.sensors:
            if sys_config.sensors.temperatures is not None:
                print(f"  [system] Temperatures (device: {ha_device_name})")
                count += 1
            if sys_config.sensors.fans is not None:
                print(f"  [system] Fans (device: {ha_device_name})")
                count += 1
        for proc in sys_config.processes:
            print(f"  [system] Process: {proc.name} (device: {ha_device_name})")
            count += 1

    print("-" * 60)
    print(f"Total: {count} entities")
    print("No MQTT connection was made.")
    return 0

    print("-" * 60)
    print("No MQTT connection was made.")
    return 0


def _resolve_device(entity_config, ha_device, ha_devices):
    """Resolve the HA device for an entity config."""
    device_key = getattr(entity_config, "device", None)
    if device_key:
        return ha_devices[device_key]
    return ha_device


def _load_entities_via_factory(
    entity_type: str, entity_configs: list, mqtt_settings, ha_device, ha_devices
) -> dict[tuple[str, str], BaseEntity]:
    """Create entities using the factory, returning a registry dict keyed by (type, id)."""
    created: dict[tuple[str, str], BaseEntity] = {}
    for config in entity_configs:
        device = _resolve_device(config, ha_device, ha_devices)
        entity = factory_create_entity(entity_type, config, mqtt_settings, device)
        entity_id = config.id or config.name
        created[(entity_type, entity_id)] = entity
    return created


def create_shared_mqtt_client(app_config) -> mqtt.Client:
    """Create a single shared paho-mqtt client for all entities."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if app_config.mqtt.username:
        client.username_pw_set(app_config.mqtt.username, app_config.mqtt.password)
    client.connect(app_config.mqtt.host, app_config.mqtt.port)
    client.loop_start()
    logger.info(
        "Shared MQTT client connected to %s:%d",
        app_config.mqtt.host,
        app_config.mqtt.port,
    )
    return client


async def run_app(config_path: str) -> None:
    """Async entry point — create entities and run them concurrently."""
    load_dotenv()

    app_config = load_config(config_path)

    # Single shared MQTT client for all entities
    shared_client = create_shared_mqtt_client(app_config)

    # Clean stale discovery messages if configured
    if app_config.mqtt.clean_start:
        clean_discovery(shared_client, app_config.hass.device_name)

    mqtt_settings = HASettings.MQTT(
        host=app_config.mqtt.host,
        port=app_config.mqtt.port,
        username=app_config.mqtt.username,
        password=app_config.mqtt.password,
        client=shared_client,
    )

    ha_device = HADeviceInfo(
        name=app_config.hass.device_name,
        identifiers=app_config.hass.device_id,
    )

    ha_devices = {}
    for device_id, device_config in app_config.devices.items():
        ha_devices[device_id] = HADeviceInfo(name=device_config.name, identifiers=device_id)

    # Create entities via factory into registry
    entity_registry: dict[tuple[str, str], BaseEntity] = {}
    entity_registry.update(
        _load_entities_via_factory("sensor", app_config.entities.sensors, mqtt_settings, ha_device, ha_devices)
    )
    entity_registry.update(
        _load_entities_via_factory(
            "binary_sensor", app_config.entities.binary_sensors, mqtt_settings, ha_device, ha_devices
        )
    )
    entity_registry.update(
        _load_entities_via_factory("switch", app_config.entities.switches, mqtt_settings, ha_device, ha_devices)
    )
    entity_registry.update(
        _load_entities_via_factory("button", app_config.entities.buttons, mqtt_settings, ha_device, ha_devices)
    )
    entity_registry.update(
        _load_entities_via_factory("select", app_config.entities.selects, mqtt_settings, ha_device, ha_devices)
    )

    # Create system entities with sub-device support
    if app_config.entities.system:
        system_entities = create_system_entities(
            app_config.entities.system,
            mqtt_settings,
            ha_device,
            sub_devices=app_config.hass.sub_devices,
            device_name=app_config.hass.device_name,
        )
        for entity in system_entities:
            # Derive system entity ID from _base_id (CompositeEntity) or _system_id (SystemSensor)
            entity_id = getattr(entity, "_base_id", None) or getattr(entity, "_system_id", "unknown")
            entity_registry[("system", entity_id)] = entity

    # Shared shutdown event
    shutdown_event = asyncio.Event()

    # Set up MQTT reconnection manager using the shared client and registry
    reconnection_manager = MQTTReconnectionManager(shared_client, entity_registry)
    logger.debug("MQTT reconnection manager initialized")

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
        for entity in entity_registry.values():
            if hasattr(entity, "stop"):
                entity.stop()
        reconnection_manager.stop()

    # Register signal handlers via the event loop
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Launch all entity run() coroutines as tasks
    tasks = [asyncio.create_task(entity.run()) for entity in entity_registry.values() if hasattr(entity, "run")]

    # Add reconnection manager as a gathered task
    tasks.append(asyncio.create_task(reconnection_manager.run()))

    logger.info("Started %d entities", len(entity_registry))

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Give tasks time to finish gracefully (5s timeout)
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=5.0)
        for task in pending:
            logger.warning("Force-cancelling task: %s", task.get_name())
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # Disconnect the shared MQTT client
    shared_client.disconnect()
    shared_client.loop_stop()

    logger.info("Shutdown complete")
