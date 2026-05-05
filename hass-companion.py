
from ha_mqtt_discoverable import Settings as HASettings
from ha_mqtt_discoverable.sensors import (
    Sensor as HASensor, 
    SensorInfo as HASensorInfo, 
    DeviceInfo as HADeviceInfo, 
    Switch as HASwitch, 
    SwitchInfo as HASwitchInfo, 
    ButtonInfo as HAButtonInfo, 
    Button as HAButton,
    BinarySensor as HABinarySensor,
    BinarySensorInfo as HABinarySensorInfo, 
    Select as HASelect,
    SelectInfo as HASelectInfo, 
)
import core.companion_entities as c_entities
import core.parsers as parsers
import core.psutil_bindings as psutil_bindings
import core.entities as core_entities
from core.config import (
    load_config,
    DEFAULT_SENSOR_INTERVAL,
    DEFAULT_BINARY_SENSOR_INTERVAL,
    DEFAULT_SWITCH_FEEDBACK_INTERVAL,
    DEFAULT_SELECT_FEEDBACK_INTERVAL,
    DEFAULT_SYSTEM_CPU_INTERVAL,
    DEFAULT_SYSTEM_MEMORY_INTERVAL,
    DEFAULT_SYSTEM_DISK_USAGE_INTERVAL,
    DEFAULT_SYSTEM_DISK_IO_INTERVAL,
    DEFAULT_SYSTEM_TEMPS_INTERVAL,
    DEFAULT_SYSTEM_FANS_INTERVAL,
)
import paho.mqtt.client as mqtt_client
import threading
import subprocess
import yaml
import time
import signal
import sys
import re
import os
import logging
import psutil
from functools import partial
from typing import Any
from paho.mqtt.client import Client, MQTTMessage
from dotenv import load_dotenv 
from bidict import bidict
from collections.abc import Iterable
import copy

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


def load_sensor(sensor_config, callback, binary = False, default_interval = None):
    if sensor_config["type"] == "command":
        # Resolve polling interval using config model if available, else dict fallback
        if default_interval is None:
            default_interval = DEFAULT_BINARY_SENSOR_INTERVAL if binary else DEFAULT_SENSOR_INTERVAL
        if hasattr(sensor_config, 'get_polling_interval'):
            polling_interval = sensor_config.get_polling_interval(default_interval)
            sensor_polling_rate = 1.0 / polling_interval
            sensor_command = sensor_config.command
            sensor_shell = sensor_config.shell
        else:
            polling_interval = sensor_config.get("polling_interval") or (
                1.0 / sensor_config["polling_rate"] if sensor_config.get("polling_rate") else default_interval
            )
            sensor_polling_rate = 1.0 / polling_interval
            sensor_command = sensor_config.get("command")
            sensor_shell = sensor_config.get("shell", "bash")
        if hasattr(sensor_config, 'get_polling_interval'):
            parser_configs = [p.model_dump() for p in sensor_config.parse]
        else:
            parser_configs = sensor_config.get("parse", [])
        pipeline = []
        for parser_config in parser_configs:
            if parser_config["type"] == "int":
                parser = parsers.IntResultParser() 
            elif parser_config["type"] == "float":
                parser = parsers.FloatResultParser() 
            elif parser_config["type"] == "bool":
                parser = parsers.BoolResultParser() 
            elif parser_config["type"] == "string":
                parser = parsers.StringResultParser()                 
            elif parser_config["type"] == "compare":
                operator = parser_config.get("operator")
                value = parser_config.get("value")
                parser = parsers.CompareResultParser(operator, value)                 
            elif parser_config["type"] == "regex":
                regex = parser_config.get("regex")
                group = parser_config.get("group")
                parser = parsers.RegexResultParser(regex, group)
            elif parser_config["type"] == "state_map":
                map = bidict(parser_config.get("map"))
                parser = parsers.StateMapResultParser(map) 

            pipeline.append(parser)
        if not binary:
            return(c_entities.CommandSensor(sensor_command, sensor_polling_rate, callback, sensor_shell, parsers=pipeline))
        else:
            return(c_entities.BinaryCommandSensor(sensor_command, sensor_polling_rate, callback, sensor_shell, parsers=pipeline))

def shutdown():
    for s in sensors:
        s.stop()

def shutdown_handler(sig, frame):
    logger.info("Termination signal received, shutting down sensors")
    shutdown()
    logger.info("All done. Exiting!")
    sys.exit(0)


def get_entity_info(entity_config):
    if "device" in entity_config:
        device = ha_devices[entity_config["device"]]
    else:
        device = ha_device

    entity_info_kwargs = {
        "name": entity_config["name"], 
        "unique_id": entity_config.get("id", entity_config["name"]),
        "device": device,
        "icon": entity_config.get("icon")
    }
    return entity_info_kwargs

def create_binary_sensor(entity_config, mqtt_settings):
    entity_info_kwargs = get_entity_info(entity_config)
    entity_info_kwargs.update({ 
        "device_class": entity_config.get("class"),
    })
    ha_entity_info = HABinarySensorInfo(**entity_info_kwargs)

    ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
    ha_entity = HABinarySensor(ha_settings)
    entity = load_sensor(entity_config, ha_entity.update_state, binary = True)
    return entity, ha_entity

def create_sensor(entity_config, mqtt_settings):
    entity_info_kwargs = get_entity_info(entity_config)
    entity_info_kwargs.update({ 
        "unit_of_measurement": entity_config.get("unit_of_measurement"),
        "device_class": entity_config.get("class"),
    })
    ha_entity_info = HASensorInfo(**entity_info_kwargs)

    ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
    ha_entity = HASensor(ha_settings)
    entity = load_sensor(entity_config, ha_entity.set_state)
    return entity, ha_entity


def create_button(entity_config, mqtt_settings):
    entity_info_kwargs = get_entity_info(entity_config)
    ha_entity_info = HAButtonInfo(**entity_info_kwargs)
        
    button_command = entity_config.get("command")
    button_shell = entity_config.get("shell", "bash")
    entity = c_entities.CommandButton(button_command, button_shell)

    ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
    def button_press_wrapper(client: Client, user_data, message: MQTTMessage):
        entity.press()
    ha_entity = HAButton(ha_settings, button_press_wrapper)
    ha_entity.write_config()
    return entity, ha_entity

def create_select(entity_config, mqtt_settings):
    entity_info_kwargs = get_entity_info(entity_config)

    state_map = bidict(entity_config.get("state_map", {}))
    options = list(state_map.keys())
    
    entity_info_kwargs["options"] = options
    ha_entity_info = HASelectInfo(**entity_info_kwargs)

    select_command_template = entity_config.get("command_template")
    select_shell = entity_config.get("shell", "bash")
    if "sensor" in entity_config:
        sensor = load_sensor(entity_config["sensor"], lambda v: logger.debug("Select sensor interim value: %s", v), default_interval=DEFAULT_SELECT_FEEDBACK_INTERVAL)
    else:
        sensor = None
    entity = c_entities.Select(select_command_template, select_shell, state_map, sensor)

    ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
    def select_callback(client: Client, user_data, message: MQTTMessage):
        value = message.payload.decode()
        entity.select(value)
    ha_entity = HASelect(ha_settings, select_callback)
    ha_entity.write_config()
    def select_option_sanitized(option):
        try:
            ha_entity.select_option(option)
        except RuntimeError as e:
            logger.error("Error selecting option: %s", e)

    entity.sensor.result_callback = select_option_sanitized
    return entity, ha_entity


def create_entity(entity_type, entity_config, mqtt_settings):
    if "device" in entity_config:
        device = ha_devices[entity_config["device"]]
    else:
        device = ha_device

    entity_info_kwargs = {
        "name": entity_config["name"], 
        "unique_id": entity_config.get("id", entity_config["name"]),
        "device": device,
        "icon": entity_config.get("icon")
    }
    entity = None
    ha_entity = None
    ha_entity_info = None

    if entity_type == "sensor":
        entity, ha_entity = create_sensor(entity_config, mqtt_settings)
    elif entity_type == "binary_sensor":
        entity, ha_entity = create_binary_sensor(entity_config, mqtt_settings)
    elif entity_type == "switch":
        ha_entity_info = HASwitchInfo(**entity_info_kwargs)

        entity_command_on = entity_config.get("command_on")
        entity_command_off = entity_config.get("command_off")
        switch_shell = entity_config.get("shell", "bash")
        if "binary_sensor" in entity_config:
            sensor = load_sensor(entity_config["binary_sensor"], lambda v: logger.debug("Switch sensor interim value: %s", v), binary = True, default_interval=DEFAULT_SWITCH_FEEDBACK_INTERVAL)
        else:
            sensor = None
        entity = c_entities.Switch(entity_command_on, entity_command_off, shell = switch_shell, sensor = sensor,)
        def switch_callback(client: Client, user_data, message: MQTTMessage):
            payload = message.payload.decode()
            if payload == "ON":
                entity.turn_on()
                # Let HA know that the switch was successfully activated
                #my_switch.on()
            elif payload == "OFF":
                entity.turn_off()
                # Let HA know that the switch was successfully deactivated
                #my_switch.off()
        ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
        ha_entity = HASwitch(ha_settings, switch_callback)
        ha_entity.off()
        def ha_set_callback(value):
            if value:
                ha_entity.on()
            else:
                ha_entity.off()
        entity.sensor.result_callback = ha_set_callback
    elif entity_type == "button":
        entity, ha_entity = create_button(entity_config, mqtt_settings)
    elif entity_type == "select":
        entity, ha_entity = create_select(entity_config, mqtt_settings)

    return entity, ha_entity

def load_entities(entity_type, entity_configs, mqtt_settings):
    entities = []
    ha_entities = []
    for entity_config in entity_configs:
        # Convert Pydantic models to dicts for existing entity creation functions
        if hasattr(entity_config, 'model_dump'):
            config_dict = entity_config.model_dump(exclude_none=True)
        else:
            config_dict = entity_config
        entity, ha_entity = create_entity(entity_type, config_dict, mqtt_settings)
        entities.append(entity)
        ha_entities.append(ha_entity)
    return entities, ha_entities

def create_ha_entity(entity_type, entity_info, mqtt):
    if entity_type == "sensor":
        ha_entity_info_class = HASensorInfo
        ha_class = HASensor
    elif entity_type == "switch":
        ha_entity_info_class = HASwitchInfo
        ha_class = HASwitch
    elif entity_type == "button":
        ha_entity_info_class = HAButtonInfo
        ha_class = HAButton
    elif entity_type == "binary_sensor":
        ha_entity_info_class = HABinarySensorInfo
        ha_class = HABinarySensor
    elif entity_type == "select":
        ha_entity_info_class = HASelectInfo
        ha_class = HASelect
    else:
        raise ValueError(f"Unknown entity type: {entity_type}")

    ha_entity_info = ha_entity_info_class(**entity_info)
    ha_settings = HASettings(mqtt = mqtt, entity = ha_entity_info)
    ha_entity = ha_class(ha_settings)
    return ha_entity

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

    sensors, ha_sensors = load_entities("sensor", app_config.entities.sensors, mqtt_settings)
    binary_sensors, ha_binary_sensors = load_entities("binary_sensor", app_config.entities.binary_sensors, mqtt_settings)
    switches, ha_switches = load_entities("switch", app_config.entities.switches, mqtt_settings)
    buttons, ha_buttons = load_entities("button", app_config.entities.buttons, mqtt_settings)
    selects, ha_selects = load_entities("select", app_config.entities.selects, mqtt_settings)
    system_entities, ha_system_entities = load_system_entities(app_config.entities.system, mqtt_settings)


    try:
        signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()
