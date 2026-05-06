from ha_mqtt_discoverable import Settings as HASettings
from ha_mqtt_discoverable.sensors import (
    DeviceInfo as HADeviceInfo,
)
from core.config import load_config
from core.factory import create_entity as factory_create_entity
import signal
import sys
import os
import logging
from dotenv import load_dotenv

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

# Global entity lists for shutdown access
entities: list = []


def shutdown():
    for entity in entities:
        if hasattr(entity, 'stop'):
            entity.stop()


def shutdown_handler(sig, frame):
    logger.info("Termination signal received, shutting down")
    shutdown()
    logger.info("All done. Exiting!")
    sys.exit(0)


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


if __name__ == "__main__":
    setup_logging()
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

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

    # Create entities via factory
    entities += load_entities_via_factory("sensor", app_config.entities.sensors, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("binary_sensor", app_config.entities.binary_sensors, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("switch", app_config.entities.switches, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("button", app_config.entities.buttons, mqtt_settings, ha_device, ha_devices)
    entities += load_entities_via_factory("select", app_config.entities.selects, mqtt_settings, ha_device, ha_devices)

    logger.info("Started %d entities", len(entities))

    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
