
from ha_mqtt_discoverable import Settings as HASettings
from ha_mqtt_discoverable.sensors import (
    DeviceInfo as HADeviceInfo,
)
import core.psutil_bindings as psutil_bindings
import core.entities as core_entities
from core.config import (
    load_config,
    DEFAULT_SYSTEM_CPU_INTERVAL,
    DEFAULT_SYSTEM_MEMORY_INTERVAL,
    DEFAULT_SYSTEM_DISK_USAGE_INTERVAL,
    DEFAULT_SYSTEM_DISK_IO_INTERVAL,
    DEFAULT_SYSTEM_TEMPS_INTERVAL,
    DEFAULT_SYSTEM_FANS_INTERVAL,
)
from core.factory import create_entity as factory_create_entity
import signal
import sys
import os
import logging
import psutil
from functools import partial
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


def shutdown():
    all_entities = sensors + binary_sensors + switches + buttons + selects + system_entities
    for entity in all_entities:
        if hasattr(entity, 'stop'):
            entity.stop()

def shutdown_handler(sig, frame):
    logger.info("Termination signal received, shutting down sensors")
    shutdown()
    logger.info("All done. Exiting!")
    sys.exit(0)


def resolve_device(entity_config):
    """Resolve the HA device for an entity config (Pydantic model)."""
    device_key = getattr(entity_config, "device", None)
    if device_key:
        return ha_devices[device_key]
    return ha_device


def load_entities_via_factory(entity_type: str, entity_configs: list, mqtt_settings) -> list:
    """Create entities using the factory, passing Pydantic configs directly."""
    entities = []
    for config in entity_configs:
        device = resolve_device(config)
        entity = factory_create_entity(entity_type, config, mqtt_settings, device)
        entities.append(entity)
    return entities

def load_system_cpu_entities(cpu_config, mqtt_settings, ha_device):
    entities = []
    cpu_rate = 1.0 / DEFAULT_SYSTEM_CPU_INTERVAL
    if "percent" in cpu_config:
        entity_info_kwargs = {
            "name": "CPU Usage",
            "unit_of_measurement": "%", 
            "unique_id": "cpu_usage",
            "icon": "mdi:cpu-64-bit",
            "device": ha_device,
        }
        if cpu_config["percent"].get("total", True):
            entity = core_entities.PollingSensor(entity_info_kwargs, mqtt_settings, function=psutil.cpu_percent, polling_rate=cpu_rate)
            entities.append(entity)
        
        if cpu_config["percent"].get("per_cpu", False):
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, partial(psutil.cpu_percent, percpu = True), polling_rate=cpu_rate)
            entities.append(entity)
    
    if "freq" in cpu_config:
        entity_info_kwargs = {
            "name": "CPU Frequency",
            "unit_of_measurement": "GHz",
            "unique_id": "cpu_freq", 
            "icon": "mdi:cpu-64-bit",
            "device": ha_device,
        }
        if cpu_config["freq"].get("total", False):
            entity = core_entities.PollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.cpu_freq, polling_rate=cpu_rate)
            entities.append(entity)
        if cpu_config["freq"].get("per_cpu", False):
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.cpu_freq, percpu = True), polling_rate=cpu_rate)
            entities.append(entity)
    return entities

def load_system_memory_entities(memory_config, mqtt_settings, ha_device):
    entities = []
    memory_rate = 1.0 / DEFAULT_SYSTEM_MEMORY_INTERVAL
    
    if "virtual" in memory_config:
        entity_info_kwargs = {
            "name": "Memory Virtual",
            "unique_id": "memory_virtual",
            "icon": "mdi:memory",
            "device": ha_device,
        }
        units = {key: "MB" for key in ["total", "available", "used", "free", "active", "inactive", "buffers", "cached", "shared", "slab", "wired"]}
        units["percent"] = "%"
        entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.virtual_memory, polling_rate=memory_rate, units_of_measurement=units)
        entities.append(entity)

    if "swap" in memory_config:
        entity_info_kwargs = {
            "name": "Memory Swap",
            "unique_id": "memory_swap",
            "icon": "mdi:swap-horizontal",
            "device": ha_device,
        }
        units = {key: "MB" for key in ["total", "used", "free"]}
        units["percent"] = "%"
        entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.swap_memory, polling_rate=memory_rate, units_of_measurement=units)
        entities.append(entity)
    return entities

def load_system_storage_entities(storage_config, mqtt_settings, ha_device):
    entities = []
    disk_usage_rate = 1.0 / DEFAULT_SYSTEM_DISK_USAGE_INTERVAL
    disk_io_rate = 1.0 / DEFAULT_SYSTEM_DISK_IO_INTERVAL
    if "usage" in storage_config:
        disks = psutil.disk_partitions()
        for disk in disks:
            entity_info_kwargs = {
                "name": f"Disk Usage {disk.device}:{disk.mountpoint}",
                "unique_id": f"disk_usage {disk.device}:{disk.mountpoint}",
                "icon": "mdi:hard-drive",
                "device": ha_device,
            }
            units = {key: "GB" for key in ["total", "used", "free"]}
            units["percent"] = "%"
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.disk_usage, disk.mountpoint), polling_rate=disk_usage_rate, units_of_measurement=units)
            entities.append(entity)
    if "io" in storage_config:
        entity_info_kwargs = {
            "name": "Disk IO",
            "unique_id": "disk_io",
            "icon": "mdi:hard-drive",
            "device": ha_device,                    
        }
        if storage_config["io"].get("total", True):
            units = {"read_count": "reads", "write_count": "writes", "read_bytes": "B", "write_bytes": "B", "read_time": "s", "write_time": "s", "busy_time": "s"}
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil.disk_io_counters, polling_rate=disk_io_rate, units_of_measurement=units)
            entities.append(entity)
            if storage_config["io"].get("rates", False):
                units = {"read_rate": "reads/s", "write_rate": "writes/s", "read_byte_rate": "B/s", "write_byte_rate": "B/s", "read_percentage": "%", "write_percentage": "%", "busy_percentage": "%"}

                entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.disk_io_rates, polling_rate=disk_io_rate, units_of_measurement=units)
                entities.append(entity)
        if storage_config["io"].get("per_disk", True):
            include = storage_config["io"].get("filters", {}).get("include", [])
            exclude = storage_config["io"].get("filters", {}).get("exclude", [])
            entity_info_kwargs = {
                "name": f"Disk IO",
                "unique_id": f"disk_io_",
                "icon": "mdi:hard-drive",
                "device": ha_device,
            }
            if storage_config["io"].get("counters", False):
                units = {"read_count": "reads", "write_count": "writes", "read_bytes": "B", "write_bytes": "B", "read_time": "s", "write_time": "s", "busy_time": "s"}
                entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.disk_io_counters, perdisk = True, include = include, exclude = exclude), polling_rate=disk_io_rate, units_of_measurement=units)
                entities.append(entity)
            if storage_config["io"].get("rates", False):
                units = {"read_rate": "reads/s", "write_rate": "writes/s", "read_byte_rate": "B/s", "write_byte_rate": "B/s", "read_percentage": "%", "write_percentage": "%", "busy_percentage": "%"}
                entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.disk_io_rates, perdisk = True, include = include, exclude = exclude), polling_rate=disk_io_rate, units_of_measurement=units)
                entities.append(entity)
    return entities


def load_system_entities(system_config, mqtt_settings):
    entities = []
    ha_entities = []
    device = ha_device

    if system_config is None:
        return entities, ha_entities

    # Convert Pydantic model to dict for existing entity creation functions
    if hasattr(system_config, 'model_dump'):
        entity_configs = system_config.model_dump(exclude_none=True)
    else:
        entity_configs = system_config
    
    if "cpu" in entity_configs:
        entities += load_system_cpu_entities(entity_configs["cpu"], mqtt_settings, device)

    if "memory" in entity_configs:
        entities += load_system_memory_entities(entity_configs["memory"], mqtt_settings, device)

    if "storage" in entity_configs:
        entities += load_system_storage_entities(entity_configs["storage"], mqtt_settings, device)

    '''if "network" in entity_configs:
        network_config = entity_configs["network"]
        if "io" in network_config:
            entity_info_kwargs = {
                "name": "Network IO",
                "unique_id": "network_io",
                "icon": "mdi:ethernet",
                "device": device,
            }
            if network_config["io"].get("total", True):
                units = {"bytes_sent": "B", "bytes_recv": "B", "packets_sent": "packets", "packets_recv": "packets", "errin": "errors", "errout": "errors", "dropin": "drops", "dropout": "drops"}
                entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.net_io_counters, polling_rate=1, units_of_measurement=units)
                entities.append(entity)
                if network_config["io"].get("rates", False):
                    units = {"bytes_sent_rate": "B/s", "bytes_recv_rate": "B/s", "packets_sent_rate": "packets/s", "packets_recv_rate": "packets/s", "errin_rate": "errors/s", "errout_rate": "errors/s", "dropin_rate": "drops/s", "dropout_rate": "drops/s"}
                    entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.net_io_rates, polling_rate=1, units_of_measurement=units)
                    entities.append(entity)
            if network_config["io"].get("per_nic", True):
                entity_info_kwargs = {
                    "name": "Network IO",
                    "unique_id": "network_io_nic",
                    "icon": "mdi:ethernet",
                    "device": device,
                }
                units = {"bytes_sent": "B", "bytes_recv": "B", "packets_sent": "packets", "packets_recv": "packets", "errin": "errors", "errout": "errors", "dropin": "drops", "dropout": "drops"}
                entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.net_io_counters, pernic = True), polling_rate=1, units_of_measurement=units)
                entities.append(entity)
                if network_config["io"].get("rates", False):
                    units = {"bytes_sent_rate": "B/s", "bytes_recv_rate": "B/s", "packets_sent_rate": "packets/s", "packets_recv_rate": "packets/s", "errin_rate": "errors/s", "errout_rate": "errors/s", "dropin_rate": "drops/s", "dropout_rate": "drops/s"}
                    entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.net_io_rates, pernic = True), polling_rate=1, units_of_measurement=units)
                    entities.append(entity)'''

    if "sensors" in entity_configs:
        sensors_config = entity_configs["sensors"]
        if "temperatures" in sensors_config:
            entity_info_kwargs = {
                "name": "Sensors Temperatures",
                "unique_id": "sensors_temperatures",
                "icon": "mdi:thermometer",
                "device": device,
            }
            units = {}
            temps_rate = 1.0 / DEFAULT_SYSTEM_TEMPS_INTERVAL
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.sensors_temperatures, polling_rate=temps_rate, units_of_measurement=units)
            entities.append(entity)

    if "fans" in entity_configs:
        fans_config = entity_configs["fans"]
        if "temperatures" in fans_config:
            entity_info_kwargs = {
                "name": "Fans Temperatures",
                "unique_id": "fans_temperatures",
                "icon": "mdi:fan",
                "device": device,
            }
            units = {}
            fans_rate = 1.0 / DEFAULT_SYSTEM_FANS_INTERVAL
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=psutil_bindings.sensors_fans, polling_rate=fans_rate, units_of_measurement=units)
            entities.append(entity)

    '''if "process" in entity_configs:
        process_config = entity_configs["process"]
        for process_name in process_config["processes"].keys():
            pattern = process_config["processes"][process_name]["pattern"]
            entity_info_kwargs = {
                "name": f"Process {process_name}",
                "unique_id": f"process_{process_name}",
                "icon": "mdi:process",
                "device": device,
            }
            units = {"status": "", "cpu_percent": "%", "memory_percent": "%", "memory_rss": "MB", "memory_vms": "MB"}
            entity = core_entities.MultiPollingSensor(entity_info_kwargs, mqtt_settings, function=partial(psutil_bindings.process_sensors, pattern), polling_rate=1, units_of_measurement=units)
            entities.append(entity)
            if "buttons" in process_config:
                process = psutil_bindings.get_process(pattern)
                if "suspend" in process_config["buttons"]:
                    entity_info_kwargs = {
                        "name": f"Process {process_name} Suspend",
                        "unique_id": f"process_{process_name}_suspend",
                        "icon": "mdi:process",
                        "device": device,
                    }
                    entity = core_entities.Button(entity_info_kwargs, mqtt_settings, function=process.suspend)
                if "resume" in process_config["buttons"]:
                    entity_info_kwargs = {
                        "name": f"Process {process_name} Resume",
                        "unique_id": f"process_{process_name}_resume",
                        "icon": "mdi:process",
                        "device": device,
                    }
                    entity = core_entities.Button(entity_info_kwargs, mqtt_settings, function=process.resume)
                if "terminate" in process_config["buttons"]:
                    entity_info_kwargs = {
                        "name": f"Process {process_name} Terminate",
                        "unique_id": f"process_{process_name}_terminate",
                        "icon": "mdi:process",
                        "device": device,
                    }
                    entity = core_entities.Button(entity_info_kwargs, mqtt_settings, function=process.terminate)
                if "kill" in process_config["buttons"]:
                    entity_info_kwargs = {
                        "name": f"Process {process_name} Kill",
                        "unique_id": f"process_{process_name}_kill",
                        "icon": "mdi:process",
                        "device": device,
                    }
                    entity = core_entities.Button(entity_info_kwargs, mqtt_settings, function=process.kill)'''


    return entities, ha_entities        
                


    
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

    # Create entities via factory (Pydantic configs passed directly)
    sensors = load_entities_via_factory("sensor", app_config.entities.sensors, mqtt_settings)
    binary_sensors = load_entities_via_factory("binary_sensor", app_config.entities.binary_sensors, mqtt_settings)
    switches = load_entities_via_factory("switch", app_config.entities.switches, mqtt_settings)
    buttons = load_entities_via_factory("button", app_config.entities.buttons, mqtt_settings)
    selects = load_entities_via_factory("select", app_config.entities.selects, mqtt_settings)

    # System entities use different patterns — keep separate for now
    system_entities, ha_system_entities = load_system_entities(app_config.entities.system, mqtt_settings)


    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
