

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
import copy

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

class Entity:
    def __init__(self, entity_type, entity_info, mqtt, create_ha_entity=True):
        self.entity_type = entity_type
        self.entity_info = entity_info
        self.mqtt = mqtt
        if create_ha_entity:
            self.ha_entity = self.create_ha_entity(entity_info)
    
    def create_ha_entity(self, entity_info):
        if self.entity_type == "sensor":
            ha_entity_info_class = HASensorInfo
            ha_class = HASensor
        elif self.entity_type == "switch":
            ha_entity_info_class = HASwitchInfo
            ha_class = HASwitch
        elif self.entity_type == "button":
            ha_entity_info_class = HAButtonInfo
            ha_class = HAButton
        elif self.entity_type == "binary_sensor":
            ha_entity_info_class = HABinarySensorInfo
            ha_class = HABinarySensor
        elif self.entity_type == "select":
            ha_entity_info_class = HASelectInfo
            ha_class = HASelect
        else:
            raise ValueError(f"Unknown entity type: {self.entity_type}")

        ha_entity_info = ha_entity_info_class(**entity_info)
        ha_settings = HASettings(mqtt = self.mqtt, entity = ha_entity_info)
        ha_entity = ha_class(ha_settings)
        return ha_entity

    def stop(self):
        pass


class PollingSensor(Entity):
    def __init__(self, entity_info, mqtt, function = None, polling_rate = 1, create_ha_entity=True, create_sensor = True):
        super().__init__("sensor", entity_info, mqtt, create_ha_entity=create_ha_entity)
        if create_sensor:
            if function is None:
                raise ValueError("Function must be provided")
            else:
                self.c_sensor = c_entities.PollingSensor(function, polling_rate, self.ha_entity.set_state)
    
    def stop(self):
        self.c_sensor.stop()
    
class MultiPollingSensor(PollingSensor):
    def __init__(self, entity_info, mqtt, function, polling_rate = 1, suffix = "{index}", units_of_measurement = None):
        super().__init__(entity_info, mqtt, create_ha_entity=False, create_sensor = False)
        function_result = function()
        if isinstance(function_result, list):
            self.ha_entity = []
            for i in range(len(function_result)):
                ha_entity_info = copy.deepcopy(entity_info)
                ha_entity_info["name"] += f" {i}"
                ha_entity_info["unique_id"] += f"_{i}"
                self.ha_entity.append(self.create_ha_entity(ha_entity_info))
            self.c_sensor = c_entities.MultiPollingSensor(function, polling_rate, [ha_entity.set_state for ha_entity in self.ha_entity])
        elif isinstance(function_result, dict):
            self.ha_entity = {}
            for key in function_result.keys():
                ha_entity_info = copy.deepcopy(entity_info)
                ha_entity_info["name"] += f" {key}"
                ha_entity_info["unique_id"] += f"_{key}"
                if units_of_measurement is not None:
                    if key in units_of_measurement.keys():
                        ha_entity_info["unit_of_measurement"] = units_of_measurement[key]
                self.ha_entity[key] = self.create_ha_entity(ha_entity_info)
            self.c_sensor = c_entities.MultiPollingSensor(function, polling_rate, {key: ha_entity.set_state for key, ha_entity in self.ha_entity.items()})

        


            
