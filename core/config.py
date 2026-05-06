"""Configuration validation models using Pydantic.

Defines typed schemas for all config.yaml sections with automatic validation.
"""

import logging
import os
import re
import sys
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)


# --- Polling interval defaults (seconds) ---

DEFAULT_SENSOR_INTERVAL = 10.0
DEFAULT_BINARY_SENSOR_INTERVAL = 5.0
DEFAULT_SWITCH_FEEDBACK_INTERVAL = 5.0
DEFAULT_SELECT_FEEDBACK_INTERVAL = 5.0
DEFAULT_SYSTEM_CPU_INTERVAL = 5.0
DEFAULT_SYSTEM_MEMORY_INTERVAL = 5.0
DEFAULT_SYSTEM_DISK_USAGE_INTERVAL = 60.0
DEFAULT_SYSTEM_DISK_IO_INTERVAL = 5.0
DEFAULT_SYSTEM_TEMPS_INTERVAL = 10.0
DEFAULT_SYSTEM_FANS_INTERVAL = 10.0
DEFAULT_SYSTEM_NETWORK_IO_INTERVAL = 5.0
DEFAULT_SYSTEM_PING_INTERVAL = 30.0
DEFAULT_SYSTEM_DNS_INTERVAL = 60.0
DEFAULT_SYSTEM_PROCESS_INTERVAL = 10.0


# --- MQTT & Hass ---

class MQTTConfig(BaseModel):
    host: str = "localhost"
    port: int = Field(default=1883, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None


class HassConfig(BaseModel):
    device_name: str
    device_id: str


class DeviceConfig(BaseModel):
    name: str


# --- Parsers ---

class ParserConfig(BaseModel):
    type: str
    regex: Optional[str] = None
    group: Optional[int] = None
    operator: Optional[str] = None
    value: Optional[float] = None
    map: Optional[dict[str, str]] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = {"int", "float", "bool", "string", "regex", "compare", "state_map"}
        if v not in valid:
            raise ValueError(f"Invalid parser type: {v}. Must be one of {valid}")
        return v


# --- Entity configs ---

class SensorConfig(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    type: str = "command"
    command: Optional[str] = None
    shell: str = "bash"
    polling_interval: Optional[float] = None
    polling_rate: Optional[float] = None
    command_timeout: float = 30.0
    device: Optional[str] = None
    device_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    icon: Optional[str] = None
    parse: list[ParserConfig] = []

    @field_validator("polling_interval")
    @classmethod
    def validate_interval(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("polling_interval must be greater than 0")
        return v

    def get_polling_interval(self, default: float) -> float:
        """Resolve effective polling interval with deprecation handling."""
        if self.polling_interval is not None:
            return self.polling_interval
        if self.polling_rate is not None:
            logger.warning(
                "'polling_rate' is deprecated, use 'polling_interval' (seconds)"
            )
            return 1.0 / self.polling_rate
        return default


class BinarySensorConfig(SensorConfig):
    pass


class SwitchConfig(BaseModel):
    name: str
    id: Optional[str] = None
    command_on: str
    command_off: str
    shell: str = "bash"
    command_timeout: float = 30.0
    device: Optional[str] = None
    icon: Optional[str] = None
    binary_sensor: Optional[BinarySensorConfig] = None


class ButtonConfig(BaseModel):
    name: str
    id: Optional[str] = None
    command: str
    shell: str = "bash"
    device: Optional[str] = None
    icon: Optional[str] = None


class SelectConfig(BaseModel):
    name: str
    id: Optional[str] = None
    command_template: str
    shell: str = "bash"
    state_map: dict[str, str] = {}
    device: Optional[str] = None
    icon: Optional[str] = None
    sensor: Optional[SensorConfig] = None


# --- System entity configs ---

class SystemCpuPercentConfig(BaseModel):
    total: bool = True
    per_cpu: bool = False


class SystemCpuFreqConfig(BaseModel):
    total: bool = False
    per_cpu: bool = False


class SystemCpuConfig(BaseModel):
    percent: Optional[SystemCpuPercentConfig] = None
    freq: Optional[SystemCpuFreqConfig] = None


class SystemMemoryConfig(BaseModel):
    virtual: Optional[dict] = None
    swap: Optional[dict] = None


class SystemStorageIOFilters(BaseModel):
    include: list[str] = []
    exclude: list[str] = []


class SystemStorageIOConfig(BaseModel):
    total: bool = True
    per_disk: bool = True
    rates: bool = False
    counters: bool = False
    filters: SystemStorageIOFilters = SystemStorageIOFilters()


class SystemStorageConfig(BaseModel):
    usage: Optional[dict] = None
    io: Optional[SystemStorageIOConfig] = None


class SystemSensorsConfig(BaseModel):
    temperatures: Optional[dict] = None
    fans: Optional[dict] = None


class NetworkIOFilters(BaseModel):
    include: list[str] = []
    exclude: list[str] = []


class NetworkIOConfig(BaseModel):
    total: bool = True
    per_nic: bool = False
    rates: bool = False
    rates_per_nic: bool = False
    polling_interval: float = DEFAULT_SYSTEM_NETWORK_IO_INTERVAL
    filters: NetworkIOFilters = NetworkIOFilters()

    @field_validator("polling_interval")
    @classmethod
    def validate_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("polling_interval must be greater than 0")
        return v


class PingHostConfig(BaseModel):
    host: str
    id: Optional[str] = None
    interface: Optional[str] = None
    timeout: float = 5.0
    size: Optional[int] = None
    polling_interval: float = DEFAULT_SYSTEM_PING_INTERVAL

    @field_validator("polling_interval")
    @classmethod
    def validate_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("polling_interval must be greater than 0")
        return v


class DNSHostConfig(BaseModel):
    host: str
    id: Optional[str] = None
    polling_interval: float = DEFAULT_SYSTEM_DNS_INTERVAL

    @field_validator("polling_interval")
    @classmethod
    def validate_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("polling_interval must be greater than 0")
        return v


class NetworkConfig(BaseModel):
    io: Optional[NetworkIOConfig] = None
    ping: list[PingHostConfig] = []
    dns: list[DNSHostConfig] = []


class ProcessConfig(BaseModel):
    name: str
    id: Optional[str] = None
    pattern: str
    polling_interval: float = DEFAULT_SYSTEM_PROCESS_INTERVAL

    @field_validator("polling_interval")
    @classmethod
    def validate_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("polling_interval must be greater than 0")
        return v


class SystemConfig(BaseModel):
    cpu: Optional[SystemCpuConfig] = None
    memory: Optional[SystemMemoryConfig] = None
    storage: Optional[SystemStorageConfig] = None
    sensors: Optional[SystemSensorsConfig] = None
    network: Optional[NetworkConfig] = None
    processes: list[ProcessConfig] = []


# --- Top-level config ---

class EntitiesConfig(BaseModel):
    sensors: list[SensorConfig] = []
    binary_sensors: list[BinarySensorConfig] = []
    switches: list[SwitchConfig] = []
    buttons: list[ButtonConfig] = []
    selects: list[SelectConfig] = []
    system: Optional[SystemConfig] = None


class AppConfig(BaseModel):
    mqtt: MQTTConfig = MQTTConfig()
    hass: HassConfig
    devices: dict[str, DeviceConfig] = {}
    entities: EntitiesConfig = EntitiesConfig()


# --- Env var resolution for YAML ---

_var_matcher = re.compile(r"\${([^}^{]+)}")
_tag_matcher = re.compile(r"[^$]*\${([^}^{]+)}.*")


def _path_constructor(_loader: Any, node: Any) -> str:
    """Resolve ${VAR} and ${VAR:default} patterns in YAML string values."""
    def replace_fn(match: re.Match) -> str:
        envparts = f"{match.group(1)}:".split(":")
        return os.environ.get(envparts[0], envparts[1])
    return _var_matcher.sub(replace_fn, node.value)


yaml.add_implicit_resolver("!envvar", _tag_matcher, None, yaml.SafeLoader)
yaml.add_constructor("!envvar", _path_constructor, yaml.SafeLoader)


# --- Config loading ---

def load_config(filepath: str) -> AppConfig:
    """Load YAML config, resolve env vars, and validate with Pydantic.

    Exits with code 1 and a clear error message on validation failure.
    """
    try:
        with open(filepath) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("Configuration file not found: %s", filepath)
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error("Failed to parse configuration file: %s", e)
        sys.exit(1)

    if raw is None:
        logger.error("Configuration file is empty: %s", filepath)
        sys.exit(1)

    try:
        return AppConfig(**raw)
    except ValidationError as e:
        logger.error("Configuration validation failed:\n%s", e)
        sys.exit(1)
