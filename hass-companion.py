import asyncio
import signal
import os
import logging

import paho.mqtt.client as mqtt
from ha_mqtt_discoverable import Settings as HASettings
from ha_mqtt_discoverable import DeviceInfo as HADeviceInfo
from dotenv import load_dotenv

from core.config import load_config
from core.discovery import clean_discovery
from core.factory import create_entity as factory_create_entity
from core.entities.system import create_system_entities
from core.mqtt import MQTTReconnectionManager

logger = logging.getLogger(__name__)


def setup_logging():
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


load_dotenv()


def resolve_device(entity_config, ha_device, ha_devices):
    """Resolve the HA device for an entity config (Pydantic model)."""
    device_key = getattr(entity_config, "device", None)
    if device_key:
        return ha_devices[device_key]
    return ha_device


def load_entities_via_factory(entity_type: str, entity_configs: list, mqtt_settings, ha_device, ha_devices) -> list:
    """Create entities using the factory, passing Pydantic configs directly."""
    created = []
    for config in entity_configs:
        device = resolve_device(config, ha_device, ha_devices)
        entity = factory_create_entity(entity_type, config, mqtt_settings, device)
        created.append(entity)
    return created


def create_shared_mqtt_client(app_config) -> mqtt.Client:
    """Create a single shared paho-mqtt client for all entities.

    Connects to the broker and starts the network loop thread.
    All ha-mqtt-discoverable entities will reuse this client instead of
    creating their own connections.
    """
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


async def main():
    """Async entry point — create entities and run them concurrently."""
    app_config = load_config('config.yaml')

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
        ha_additional_device_info = HADeviceInfo(name=device_config.name, identifiers=device_id)
        ha_devices[device_id] = ha_additional_device_info

    # Create entities via factory (sync init is fine)
    entities: list = []
    entities += load_entities_via_factory("sensor", app_config.entities.sensors, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("binary_sensor", app_config.entities.binary_sensors, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("switch", app_config.entities.switches, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("button", app_config.entities.buttons, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("select", app_config.entities.selects, mqtt_settings, ha_device, ha_devices)

    # Create system entities with sub-device support
    if app_config.entities.system:
        entities += create_system_entities(
            app_config.entities.system, mqtt_settings, ha_device,
            sub_devices=app_config.hass.sub_devices,
            device_name=app_config.hass.device_name,
        )

    # Shared shutdown event
    shutdown_event = asyncio.Event()

    # Set up MQTT reconnection manager using the shared client
    reconnection_manager = MQTTReconnectionManager(shared_client, entities)
    logger.info("MQTT reconnection manager initialized")

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
        for entity in entities:
            if hasattr(entity, 'stop'):
                entity.stop()
        reconnection_manager.stop()

    # Register signal handlers via the event loop
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Launch all entity run() coroutines as tasks
    tasks = [asyncio.create_task(entity.run()) for entity in entities if hasattr(entity, 'run')]

    # Add reconnection manager as a gathered task
    tasks.append(asyncio.create_task(reconnection_manager.run()))

    logger.info("Started %d entities", len(entities))

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


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
