
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
from typing import Any
from paho.mqtt.client import Client, MQTTMessage
from dotenv import load_dotenv 
load_dotenv() 

_var_matcher = re.compile(r"\${([^}^{]+)}")
_tag_matcher = re.compile(r"[^$]*\${([^}^{]+)}.*")


def _path_constructor(_loader: Any, node: Any):
    def replace_fn(match):
        envparts = f"{match.group(1)}:".split(":")
        return os.environ.get(envparts[0], envparts[1])
    return _var_matcher.sub(replace_fn, node.value)

yaml.add_implicit_resolver("!envvar", _tag_matcher, None, yaml.SafeLoader)
yaml.add_constructor("!envvar", _path_constructor, yaml.SafeLoader)

class Config:
    def __init__(self, filepath):
        self.filepath = filepath
        self.load_config()

    def load_config(self):
        #grab dictionary from config.yaml:
        with open(self.filepath, 'r') as file:
            self.config_dict = yaml.safe_load(file)

class ResultParser:
    def __init__(self):
        pass
    def parse(self, text):
        return text

class IntResultParser(ResultParser):
    def parse(self, text):
        return int(text)

class FloatResultParser(ResultParser):
    def parse(self, text):
        return float(text)

class BoolResultParser(ResultParser):
    def parse(self, text):
        if str(text).lower() in ['true', '1', 't', 'y', 'yes']:
            return True
        elif str(text).lower() in ['false', '0', 'f', 'n', 'no']:
            return False
        else:
            return False

class StringResultParser(ResultParser):
    def parse(self, text):
        return str(text)

class CompareResultParser(ResultParser):
    def __init__(self, compare_value, operator):
        self.compare_value = compare_value
        self.operator = operator
        # Check operator validity:
        if operator not in ['<', '>', '<=', '>=', '==', '!=']:
            raise ValueError("Invalid operator")
        
    def parse(self, value):
        
        if self.operator == '<':
            return value < self.compare_value
        elif self.operator == '>':
            return value > self.compare_value
        elif self.operator == '<=':
            return value <= self.compare_value
        elif self.operator == '>=':
            return value >= self.compare_value
        elif self.operator == '==':
            return value == self.compare_value
        elif self.operator == '!=':
            return value != self.compare_value


class RegexResultParser(ResultParser):
    def __init__(self, regex, group = None):
        self.regex = regex
        self.group = group
    def parse(self, text):
        import re
        match = re.search(self.regex, str(text))
        if match:
            if self.group is not None:
                return match.group(self.group)
            else:
                return match.group(0)
        else:
            return None

class Sensor():
    def __init__(self, result_callback):
        self.result_callback = result_callback
    def update(self, value):
        self.result_callback(value)
    def stop(self):
        pass
    

class OptimisticSensor(Sensor):
    def __init__(self):
        self.state = None
        def null_function(value):
            pass
        super().__init__(null_function)
    def update(self, value):
        self.state = value

class BinarySensor(Sensor):
    def update(self, value):
        if isinstance(value, bool):
            super().update(value)
        else:
            raise ValueError('Invalid binary sensor value')
    def on(self):
        self.update(True)
    def off(self):
        self.update(False)
    

class CommandSensor(Sensor):
    def __init__(self, command, polling_rate, result_callback, shell, parsers = []):
        self.command = command
        self.polling_rate = polling_rate
        self.polling_time = 1.0/polling_rate
        self.exit = threading.Event()
        self.thread = threading.Thread(target = self.polling_thread, daemon = True)
        self.shell = shell
        self.parsers = parsers
        super().__init__(result_callback)
        self.start()

    def start(self):
        print("Starting command sensor")
        self.thread.start()

    def polling_thread(self):
        while not self.exit.is_set():
            # execute command
            self.update(subprocess.run([self.shell, "-c", self.command], stdout = subprocess.PIPE).stdout.decode("utf-8"))
            
            # wait for next polling time
            self.exit.wait(timeout = self.polling_time)
    
    def pre_process_result(self, result):
        if isinstance(result, str): # remove trailing newline character from result string
            return(result.rstrip("\n"))

    def update(self, value):
        
        result = self.pre_process_result(value)
        for p in self.parsers:
            result = p.parse(result) # apply parsers to result
        self.result_callback(result)
        print("Updating Sensor. Raw value: ", value, "Parsed value: ", result)

    def stop(self):
        self.exit.set()

class BinaryCommandSensor(CommandSensor, BinarySensor):
    pass


class Switch:
    def __init__(self, command_on, command_off, shell, sensor = None):
        self.command_on = command_on
        self.command_off = command_off
        self.shell = "bash"
        if sensor is None:
            self.sensor = OptimisticSensor()
        else:
            self.sensor = sensor

    def turn_on(self):
        subprocess.run([self.shell, "-c", self.command_on], stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.sensor.update("True")

    def turn_off(self):
        subprocess.run([self.shell, "-c", self.command_off], stdout=subprocess.PIPE).stdout.decode("utf-8")
        self.sensor.update("False")
    
    def stop(self):
        self.sensor.stop()

class Button:
    def __init__(self, command, shell):
        self.command = command
        self.shell = shell

    def press(self):
        subprocess.run([self.shell, "-c", self.command], stdout=subprocess.PIPE).stdout.decode("utf-8")


'''class Select:
    def __init__(self, command_template, shell, state_mapping = {}, sensor = None):
        self.command_template = command_template
        self.shell = shell
        self.state_mapping = state_mapping
        if sensor is None:
            self.sensor = OptimisticSensor()
        else:
            self.sensor = sensor

    def select(self, value):
        subprocess.run([self.shell, "-c", self.command_template.format(value)], stdout=subprocess.PIPE).stdout.decode("utf-8")
        mapped_value  = self.state_mapping.get(value, value)
        self.sensor.update(mapped_value)
    
    def stop(self):
        self.sensor.stop()'''

def load_sensor(sensor_config, callback, binary = False):
    if sensor_config["type"] == "command":
        sensor_polling_rate = sensor_config.get("polling_rate", 1)
        sensor_command = sensor_config.get("command")
        sensor_shell = sensor_config.get("shell", "bash")
        parser_configs = sensor_config.get("parse", [])
        parsers = []
        for parser_config in parser_configs:
            if parser_config["type"] == "int":
                parser = IntResultParser() 
            elif parser_config["type"] == "float":
                parser = FloatResultParser() 
            elif parser_config["type"] == "bool":
                parser = BoolResultParser() 
            elif parser_config["type"] == "string":
                parser = StringResultParser()                 
            elif parser_config["type"] == "compare":
                operator = parser_config.get("operator")
                value = parser_config.get("value")
                parser = CompareResultParser(operator, value)                 
            elif parser_config["type"] == "regex":
                regex = parser_config.get("regex")
                group = parser_config.get("group")
                parser = RegexResultParser(regex, group)
            parsers.append(parser)
        if not binary:
            return(CommandSensor(sensor_command, sensor_polling_rate, callback, sensor_shell, parsers=parsers))
        else:
            return(BinaryCommandSensor(sensor_command, sensor_polling_rate, callback, sensor_shell, parsers=parsers))

def shutdown():
    for s in sensors:
        s.stop()

def shutdown_handler(sig, frame):
    print("Termination Signal received. Shutting down Sensors")
    shutdown()
    print("All Done. Exiting!")
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


def create_button(entity_config, mqtt_settings):
    entity_info_kwargs = get_entity_info(entity_config)
    ha_entity_info = HAButtonInfo(**entity_info_kwargs)
        
    button_command = entity_config.get("command")
    button_shell = entity_config.get("shell", "bash")
    entity = Button(button_command, button_shell)

    ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
    def button_press_wrapper(client: Client, user_data, message: MQTTMessage):
        entity.press()
    ha_entity = HAButton(ha_settings, button_press_wrapper)
    ha_entity.write_config()
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
        entity_info_kwargs.update({ 
            "unit_of_measurement": entity_config.get("unit_of_measurement"),
            "device_class": entity_config.get("class"),
        })
        ha_entity_info = HASensorInfo(**entity_info_kwargs)

        ha_settings = HASettings(mqtt = mqtt_settings, entity = ha_entity_info)
        ha_entity = HASensor(ha_settings)
        entity = load_sensor(entity_config, ha_entity.set_state)
    elif entity_type == "binary_sensor":
        entity, ha_entity = create_binary_sensor(entity_config, mqtt_settings)
    elif entity_type == "switch":
        ha_entity_info = HASwitchInfo(**entity_info_kwargs)

        entity_command_on = entity_config.get("command_on")
        entity_command_off = entity_config.get("command_off")
        switch_shell = entity_config.get("shell", "bash")
        if "binary_sensor" in entity_config:
            sensor = load_sensor(entity_config["binary_sensor"], print, binary = True)
        else:
            sensor = None
        entity = Switch(entity_command_on, entity_command_off, shell = switch_shell, sensor = sensor,)
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

    return entity, ha_entity

def load_entities(entity_type, entity_configs, mqtt_settings):
    entities = []
    ha_entities = []
    for entity_config in entity_configs:
        entity, ha_entity = create_entity(entity_type, entity_config, mqtt_settings)
        entities.append(entity)
        ha_entities.append(ha_entity)
    return entities, ha_entities


    
if __name__ == "__main__":

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    config = Config('config.yaml')
    mqtt_config = config.config_dict["mqtt"]
    mqtt_settings = HASettings.MQTT(
        host = mqtt_config.get("host", "localhost"), 
        port = mqtt_config.get("port", 1883), 
        username = mqtt_config.get("username"), 
        password = mqtt_config.get("password")
    )
    ha_config = config.config_dict["hass"]
    ha_device = HADeviceInfo(name=ha_config.get("device_name", "Hass Companion"), identifiers=ha_config.get("device_id", "hass-companion"))

    device_configs = config.config_dict.get("devices", {})
    ha_devices = {}
    for device_id, device_config in device_configs.items():
        ha_additional_device_info = HADeviceInfo(name=device_config.get("name", device_id), identifiers=device_id)
        ha_devices[device_id] = ha_additional_device_info


    sensors, ha_sensors = load_entities("sensor", config.config_dict["entities"].get("sensors", []), mqtt_settings)
    binary_sensors, ha_binary_sensors = load_entities("binary_sensor", config.config_dict["entities"].get("binary_sensors", []), mqtt_settings)
    switches, ha_switches = load_entities("switch", config.config_dict["entities"].get("switches", []), mqtt_settings)
    buttons, ha_buttons = load_entities("button", config.config_dict["entities"].get("buttons", []), mqtt_settings)


    while True:
        pass
    shutdown()
    
    


        