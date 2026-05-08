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
from core.entities.config_status import ConfigStatusSensor
from core.entities.system import create_system_entities
from core.factory import create_entity as factory_create_entity
from core.mqtt import MQTTReconnectionManager
from core.reload import ReloadManager
from core.watcher import ConfigFileWatcher

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
    """Create a single shared paho-mqtt client for all entities.

    Configures LWT (Last Will and Testament) so the broker publishes "offline"
    to the device status topic if the client disconnects unexpectedly.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if app_config.mqtt.username:
        client.username_pw_set(app_config.mqtt.username, app_config.mqtt.password)

    # Set LWT before connect — broker publishes this on unexpected disconnect
    status_topic = f"hmd/{app_config.hass.device_id}/status"
    client.will_set(status_topic, "offline", qos=1, retain=True)

    client.connect(app_config.mqtt.host, app_config.mqtt.port)
    client.loop_start()

    # Publish online (retained) — overrides any previous LWT "offline"
    client.publish(status_topic, "online", qos=1, retain=True)

    logger.info(
        "Shared MQTT client connected to %s:%d (status: %s)",
        app_config.mqtt.host,
        app_config.mqtt.port,
        status_topic,
    )
    return client


async def run_app(config_path: str, watch_config: bool = False) -> None:
    """Async entry point — create entities and run them concurrently.

    Supports hot-reload via SIGHUP signal. When reload is triggered,
    the ReloadManager diffs configs and applies changes without restart.
    """
    load_dotenv()

    app_config = load_config(config_path)

    # Single shared MQTT client for all entities
    shared_client = create_shared_mqtt_client(app_config)

    # Clean stale discovery messages if configured
    if app_config.mqtt.clean_start:
        clean_discovery(shared_client, app_config.hass.device_name)

    # Configure device status topic for entity availability (must be before entity creation)
    from core.ha_entities import configure_device_status_topic

    device_status_topic = f"hmd/{app_config.hass.device_id}/status"
    configure_device_status_topic(device_status_topic)

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

    # Create built-in ConfigStatusSensor (excluded from reconciliation)
    config_status_sensor = ConfigStatusSensor(
        mqtt_settings, ha_device, device_id=app_config.hass.device_id
    )

    # Shared events
    shutdown_event = asyncio.Event()
    reload_event = asyncio.Event()

    # Set up MQTT reconnection manager using the shared client and registry
    # Include config_status_sensor in the reconnection cycle
    reconnection_manager = MQTTReconnectionManager(shared_client, entity_registry)
    reconnection_manager._config_status_sensor = config_status_sensor
    logger.debug("MQTT reconnection manager initialized")

    # Set up ReloadManager
    reload_manager = ReloadManager(
        config_path=config_path,
        mqtt_settings=mqtt_settings,
        ha_device=ha_device,
        ha_devices=ha_devices,
        sub_devices=app_config.hass.sub_devices,
        device_name=app_config.hass.device_name,
    )

    # Set up config file watcher if requested
    watcher: ConfigFileWatcher | None = None
    watcher_task: asyncio.Task | None = None

    def shutdown_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
        for entity in entity_registry.values():
            if hasattr(entity, "stop"):
                entity.stop()
        reconnection_manager.stop()
        if watcher:
            watcher.stop()

    def sighup_handler():
        logger.info("SIGHUP received — scheduling config reload")
        reload_event.set()

    # Register signal handlers via the event loop
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_handler)
    loop.add_signal_handler(signal.SIGHUP, sighup_handler)

    # Start file watcher if enabled
    if watch_config:

        async def _watcher_callback() -> None:
            logger.info("Config file changed — scheduling reload")
            reload_event.set()

        watcher = ConfigFileWatcher(config_path, _watcher_callback)
        watcher_task = asyncio.create_task(watcher.run())
        logger.info("Config file watcher enabled for %s", config_path)

    # Launch all entity run() coroutines as tasks
    entity_tasks: list[asyncio.Task] = [
        asyncio.create_task(entity.run()) for entity in entity_registry.values() if hasattr(entity, "run")
    ]

    # Add reconnection manager as a gathered task
    reconnection_task = asyncio.create_task(reconnection_manager.run())

    logger.info("Started %d entities", len(entity_registry))

    # Main loop: wait for shutdown or reload events
    while not shutdown_event.is_set():
        # Wait for either shutdown or reload
        reload_wait = asyncio.create_task(reload_event.wait())
        shutdown_wait = asyncio.create_task(shutdown_event.wait())

        done, pending = await asyncio.wait(
            [reload_wait, shutdown_wait],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel the pending waiter
        for task in pending:
            task.cancel()

        if shutdown_event.is_set():
            break

        if reload_event.is_set():
            reload_event.clear()
            result = await reload_manager.reload(entity_registry, app_config)

            if result.success:
                # Cancel old entity tasks
                for task in entity_tasks:
                    task.cancel()
                await asyncio.gather(*entity_tasks, return_exceptions=True)

                # Update registry and config
                entity_registry.clear()
                entity_registry.update(result.new_entities)
                app_config = result.new_config

                # Update reconnection manager's entity reference
                reconnection_manager._entities = entity_registry

                # Start new entity tasks
                entity_tasks = [
                    asyncio.create_task(entity.run())
                    for entity in entity_registry.values()
                    if hasattr(entity, "run")
                ]

                logger.info(
                    "Reload complete: %d added, %d removed, %d updated",
                    len(result.added),
                    len(result.removed),
                    len(result.updated),
                )
                for name in result.added:
                    logger.debug("  Added: %s", name)
                for name in result.removed:
                    logger.debug("  Removed: %s", name)
                for name in result.updated:
                    logger.debug("  Updated: %s", name)

                if result.restart_reasons:
                    for reason in result.restart_reasons:
                        logger.warning("  Restart required: %s", reason)
                    config_status_sensor.set_restart_required(
                        added=len(result.added),
                        removed=len(result.removed),
                        updated=len(result.updated),
                        reasons=result.restart_reasons,
                    )
                else:
                    config_status_sensor.set_valid(
                        added=len(result.added),
                        removed=len(result.removed),
                        updated=len(result.updated),
                    )
            else:
                logger.warning("Reload failed: %s", result.error)
                config_status_sensor.set_error(result.error)

    # Shutdown: stop all entity tasks
    for task in entity_tasks:
        task.cancel()
    reconnection_task.cancel()
    if watcher_task:
        watcher_task.cancel()

    all_tasks = entity_tasks + [reconnection_task]
    if watcher_task:
        all_tasks.append(watcher_task)
    if all_tasks:
        done, pending = await asyncio.wait(all_tasks, timeout=5.0)
        for task in pending:
            logger.warning("Force-cancelling task: %s", task.get_name())
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # Publish offline before disconnecting (graceful shutdown)
    shared_client.publish(device_status_topic, "offline", qos=1, retain=True)

    # Disconnect the shared MQTT client
    shared_client.disconnect()
    shared_client.loop_stop()

    logger.info("Shutdown complete")
