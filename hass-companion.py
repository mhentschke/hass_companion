import asyncio
import signal
import os
import logging

from ha_mqtt_discoverable import Settings as HASettings
from ha_mqtt_discoverable.sensors import (
    DeviceInfo as HADeviceInfo,
)
from dotenv import load_dotenv

from core.config import load_config
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


def _disconnect_mqtt_clients(entities: list) -> None:
    """Disconnect all MQTT clients from ha-mqtt-discoverable entities.

    Each HA entity created by ha-mqtt-discoverable has an internal paho-mqtt
    client with loop_start() running. We must stop these to allow clean exit.
    """
    seen_clients = set()
    for entity in entities:
        # Single entities (Entity subclasses)
        ha_entity = getattr(entity, '_ha_entity', None)
        if ha_entity:
            client = getattr(ha_entity, 'mqtt_client', None)
            if client and id(client) not in seen_clients:
                seen_clients.add(id(client))
                try:
                    client.disconnect()
                    client.loop_stop()
                except Exception:
                    pass
        # Composite entities (SystemMultiSensor) have multiple HA entities
        ha_entities = getattr(entity, '_ha_entities', None)
        if ha_entities and isinstance(ha_entities, dict):
            for ha_ent in ha_entities.values():
                client = getattr(ha_ent, 'mqtt_client', None)
                if client and id(client) not in seen_clients:
                    seen_clients.add(id(client))
                    try:
                        client.disconnect()
                        client.loop_stop()
                    except Exception:
                        pass


def _get_mqtt_client(entities: list):
    """Extract a paho-mqtt client from the first available entity.

    Used by the reconnection manager to monitor connection state.
    Returns None if no MQTT client is found.
    """
    for entity in entities:
        ha_entity = getattr(entity, '_ha_entity', None)
        if ha_entity:
            client = getattr(ha_entity, 'mqtt_client', None)
            if client:
                return client
        ha_entities = getattr(entity, '_ha_entities', None)
        if ha_entities and isinstance(ha_entities, dict):
            for ha_ent in ha_entities.values():
                client = getattr(ha_ent, 'mqtt_client', None)
                if client:
                    return client
    return None


async def main():
    """Async entry point — create entities and run them concurrently."""
    app_config = load_config('config.yaml')

    mqtt_settings = HASettings.MQTT(
        host=app_config.mqtt.host,
        port=app_config.mqtt.port,
        username=app_config.mqtt.username,
        password=app_config.mqtt.password,
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

    # Create system entities
    if app_config.entities.system:
        entities += create_system_entities(app_config.entities.system, mqtt_settings, ha_device)

    # Shared shutdown event
    shutdown_event = asyncio.Event()

    # Set up MQTT reconnection manager
    reconnection_manager = None
    mqtt_client = _get_mqtt_client(entities)
    if mqtt_client:
        reconnection_manager = MQTTReconnectionManager(mqtt_client, entities)
        logger.info("MQTT reconnection manager initialized")
    else:
        logger.warning("No MQTT client found — reconnection manager disabled")

    def signal_handler():
        logger.info("Shutdown signal received")
        shutdown_event.set()
        for entity in entities:
            if hasattr(entity, 'stop'):
                entity.stop()
        if reconnection_manager:
            reconnection_manager.stop()

    # Register signal handlers via the event loop
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Launch all entity run() coroutines as tasks
    tasks = [asyncio.create_task(entity.run()) for entity in entities if hasattr(entity, 'run')]

    # Add reconnection manager as a gathered task
    if reconnection_manager:
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
        # Await cancelled tasks to suppress warnings
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    # Disconnect all MQTT clients to allow clean process exit
    _disconnect_mqtt_clients(entities)

    logger.info("Shutdown complete")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
