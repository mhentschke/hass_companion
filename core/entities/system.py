"""System entities — psutil-based monitoring using the unified entity architecture.

SystemMultiSensor extends CompositeEntity for callables returning dict/list.
create_system_entities() is the factory that interprets SystemConfig.
"""

import logging
from functools import partial
from typing import Any, Callable

import psutil

import core.psutil_bindings as psutil_bindings
from core.config import (
    DEFAULT_SYSTEM_CPU_INTERVAL,
    DEFAULT_SYSTEM_DISK_IO_INTERVAL,
    DEFAULT_SYSTEM_DISK_USAGE_INTERVAL,
    DEFAULT_SYSTEM_FANS_INTERVAL,
    DEFAULT_SYSTEM_MEMORY_INTERVAL,
    DEFAULT_SYSTEM_NETWORK_IO_INTERVAL,
    DEFAULT_SYSTEM_PROCESS_INTERVAL,
    DEFAULT_SYSTEM_TEMPS_INTERVAL,
    SystemConfig,
)
from core.rate import RateCalculator
from core.entities.base import CompositeEntity
from core.entities.fetcher import SystemFetcher
from core.entities.sensor import SystemSensor

logger = logging.getLogger(__name__)


class SystemMultiSensor(CompositeEntity):
    """CompositeEntity backed by a Python callable returning dict or list.

    Probes the callable once to discover result shape, creates one HA sensor
    per key/index, then polls at the configured interval distributing values.
    """

    def __init__(
        self,
        mqtt_settings,
        device,
        *,
        name: str,
        unique_id: str,
        fn: Callable,
        interval: float,
        icon: str | None = None,
        units: dict[str, str] | None = None,
        _ha_entities: dict[str, Any] | None = None,
    ):
        super().__init__(
            mqtt_settings, device,
            name=name, unique_id=unique_id, icon=icon, units=units,
        )
        self._fn = fn
        self._interval = interval

        # Probe function to discover result shape
        initial_result = fn()

        # Use injected HA entities (for testing) or create real ones
        if _ha_entities is not None:
            self._ha_entities = _ha_entities
        else:
            self._create_ha_entities(initial_result)

        # Single fetcher distributes to all HA entities
        self._fetcher = SystemFetcher(
            callback=self._distribute_values,
            fn=fn,
            interval=interval,
        )

    def _create_ha_entities(self, sample_result) -> None:
        """Create one HA sensor per key (dict) or index (list)."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Sensor as HASensor,
            SensorInfo as HASensorInfo,
        )

        if isinstance(sample_result, dict):
            keys = list(sample_result.keys())
        elif isinstance(sample_result, list):
            keys = [str(i) for i in range(len(sample_result))]
        else:
            # Scalar — shouldn't use MultiSensor, but handle gracefully
            keys = ["value"]

        for key in keys:
            entity_name = f"{self._base_name} {key}"
            entity_id = f"{self._base_id}_{key}"
            unit = self._units.get(key)

            entity_info = HASensorInfo(
                name=entity_name,
                unique_id=entity_id,
                device=self._device,
                icon=self._icon,
                unit_of_measurement=unit,
            )
            settings = HASettings(mqtt=self._mqtt_settings, entity=entity_info)
            self._ha_entities[key] = HASensor(settings)



def create_system_entities(system_config: SystemConfig | None, mqtt_settings, device) -> list:
    """Interpret SystemConfig and create all system entities.

    Returns a flat list of SystemSensor and SystemMultiSensor instances.
    Each has a stop() method for clean shutdown.
    """
    if system_config is None:
        return []

    entities: list = []

    # Convert Pydantic model to dict for section inspection
    if hasattr(system_config, "model_dump"):
        config_dict = system_config.model_dump(exclude_none=True)
    else:
        config_dict = system_config

    # --- CPU ---
    if "cpu" in config_dict:
        cpu = config_dict["cpu"]
        interval = DEFAULT_SYSTEM_CPU_INTERVAL

        if "percent" in cpu:
            if cpu["percent"].get("total", True):
                entities.append(SystemSensor(
                    mqtt_settings, device,
                    fn=psutil.cpu_percent,
                    name="CPU Usage",
                    unique_id="cpu_usage",
                    interval=interval,
                    icon="mdi:cpu-64-bit",
                    unit_of_measurement="%",
                ))

            if cpu["percent"].get("per_cpu", False):
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="CPU Usage",
                    unique_id="cpu_usage_per_cpu",
                    fn=partial(psutil.cpu_percent, percpu=True),
                    interval=interval,
                    icon="mdi:cpu-64-bit",
                    units={},  # All entries are %
                ))

        if "freq" in cpu:
            if cpu["freq"].get("total", False):
                entities.append(SystemSensor(
                    mqtt_settings, device,
                    fn=psutil_bindings.cpu_freq,
                    name="CPU Frequency",
                    unique_id="cpu_freq",
                    interval=interval,
                    icon="mdi:cpu-64-bit",
                    unit_of_measurement="GHz",
                ))

            if cpu["freq"].get("per_cpu", False):
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="CPU Frequency",
                    unique_id="cpu_freq_per_cpu",
                    fn=partial(psutil_bindings.cpu_freq, percpu=True),
                    interval=interval,
                    icon="mdi:cpu-64-bit",
                    units={},
                ))

    # --- Memory ---
    if "memory" in config_dict:
        memory = config_dict["memory"]
        interval = DEFAULT_SYSTEM_MEMORY_INTERVAL

        if "virtual" in memory:
            units = {k: "MB" for k in [
                "total", "available", "used", "free", "active",
                "inactive", "buffers", "cached", "shared", "slab", "wired",
            ]}
            units["percent"] = "%"
            entities.append(SystemMultiSensor(
                mqtt_settings, device,
                name="Memory Virtual",
                unique_id="memory_virtual",
                fn=psutil_bindings.virtual_memory,
                interval=interval,
                icon="mdi:memory",
                units=units,
            ))

        if "swap" in memory:
            units = {k: "MB" for k in ["total", "used", "free"]}
            units["percent"] = "%"
            entities.append(SystemMultiSensor(
                mqtt_settings, device,
                name="Memory Swap",
                unique_id="memory_swap",
                fn=psutil_bindings.swap_memory,
                interval=interval,
                icon="mdi:swap-horizontal",
                units=units,
            ))

    # --- Storage ---
    if "storage" in config_dict:
        storage = config_dict["storage"]

        if "usage" in storage:
            disk_interval = DEFAULT_SYSTEM_DISK_USAGE_INTERVAL
            for disk in psutil.disk_partitions():
                units = {k: "GB" for k in ["total", "used", "free"]}
                units["percent"] = "%"
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name=f"Disk Usage {disk.device}:{disk.mountpoint}",
                    unique_id=f"disk_usage_{disk.device}_{disk.mountpoint}",
                    fn=partial(psutil_bindings.disk_usage, disk.mountpoint),
                    interval=disk_interval,
                    icon="mdi:harddisk",
                    units=units,
                ))

        if "io" in storage:
            io_config = storage["io"]
            io_interval = DEFAULT_SYSTEM_DISK_IO_INTERVAL
            include = io_config.get("filters", {}).get("include", [])
            exclude = io_config.get("filters", {}).get("exclude", [])

            if io_config.get("total", True):
                units = {
                    "read_count": "reads", "write_count": "writes",
                    "read_bytes": "B", "write_bytes": "B",
                    "read_time": "s", "write_time": "s", "busy_time": "s",
                }
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Disk IO",
                    unique_id="disk_io",
                    fn=psutil_bindings.disk_io_counters,
                    interval=io_interval,
                    icon="mdi:harddisk",
                    units=units,
                ))

            if io_config.get("rates", False):
                units = {
                    "read_rate": "reads/s", "write_rate": "writes/s",
                    "read_byte_rate": "B/s", "write_byte_rate": "B/s",
                    "read_percentage": "%", "write_percentage": "%",
                    "busy_percentage": "%",
                }
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Disk IO Rates",
                    unique_id="disk_io_rates",
                    fn=psutil_bindings.disk_io_rates,
                    interval=io_interval,
                    icon="mdi:harddisk",
                    units=units,
                ))

            if io_config.get("per_disk", True) and io_config.get("counters", False):
                units = {
                    "read_count": "reads", "write_count": "writes",
                    "read_bytes": "B", "write_bytes": "B",
                    "read_time": "s", "write_time": "s", "busy_time": "s",
                }
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Disk IO Per Disk",
                    unique_id="disk_io_per_disk",
                    fn=partial(
                        psutil_bindings.disk_io_counters,
                        perdisk=True, include=include, exclude=exclude,
                    ),
                    interval=io_interval,
                    icon="mdi:harddisk",
                    units=units,
                ))

            if io_config.get("per_disk", True) and io_config.get("rates", False):
                units = {
                    "read_rate": "reads/s", "write_rate": "writes/s",
                    "read_byte_rate": "B/s", "write_byte_rate": "B/s",
                    "read_percentage": "%", "write_percentage": "%",
                    "busy_percentage": "%",
                }
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Disk IO Rates Per Disk",
                    unique_id="disk_io_rates_per_disk",
                    fn=partial(
                        psutil_bindings.disk_io_rates,
                        perdisk=True, include=include, exclude=exclude,
                    ),
                    interval=io_interval,
                    icon="mdi:harddisk",
                    units=units,
                ))

    # --- Sensors (temperatures, fans) ---
    if "sensors" in config_dict:
        sensors = config_dict["sensors"]

        if "temperatures" in sensors:
            entities.append(SystemMultiSensor(
                mqtt_settings, device,
                name="Sensors Temperatures",
                unique_id="sensors_temperatures",
                fn=psutil_bindings.sensors_temperatures,
                interval=DEFAULT_SYSTEM_TEMPS_INTERVAL,
                icon="mdi:thermometer",
                units={},
            ))

        if "fans" in sensors:
            entities.append(SystemMultiSensor(
                mqtt_settings, device,
                name="Sensors Fans",
                unique_id="sensors_fans",
                fn=psutil_bindings.sensors_fans,
                interval=DEFAULT_SYSTEM_FANS_INTERVAL,
                icon="mdi:fan",
                units={},
            ))

    # --- Network IO ---
    if "network" in config_dict:
        network = config_dict["network"]
        if "io" in network:
            io_config = network["io"]
            io_interval = io_config.get("polling_interval", DEFAULT_SYSTEM_NETWORK_IO_INTERVAL)
            include = io_config.get("filters", {}).get("include", [])
            exclude = io_config.get("filters", {}).get("exclude", [])

            if io_config.get("total", True):
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Network IO",
                    unique_id="network_io",
                    fn=psutil_bindings.net_io_counters_total,
                    interval=io_interval,
                    icon="mdi:network",
                    units={
                        "bytes_sent": "MB", "bytes_recv": "MB",
                        "packets_sent": "packets", "packets_recv": "packets",
                        "errin": "errors", "errout": "errors",
                        "dropin": "drops", "dropout": "drops",
                    },
                ))

            if io_config.get("per_nic", False):
                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Network IO Per NIC",
                    unique_id="network_io_per_nic",
                    fn=partial(
                        psutil_bindings.net_io_counters_per_nic,
                        include=include, exclude=exclude,
                    ),
                    interval=io_interval,
                    icon="mdi:network",
                    units={},
                ))

            if io_config.get("rates", False):
                rate_calc = RateCalculator()

                def _net_io_rates_total(rc=rate_calc):
                    counters = psutil_bindings.net_io_counters_total()
                    return rc.update(counters)

                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Network IO Rates",
                    unique_id="network_io_rates",
                    fn=_net_io_rates_total,
                    interval=io_interval,
                    icon="mdi:network",
                    units={
                        "bytes_sent": "MB/s", "bytes_recv": "MB/s",
                        "packets_sent": "packets/s", "packets_recv": "packets/s",
                        "errin": "errors/s", "errout": "errors/s",
                        "dropin": "drops/s", "dropout": "drops/s",
                    },
                ))

            if io_config.get("rates_per_nic", False):
                rate_calc_per_nic = RateCalculator()

                def _net_io_rates_per_nic(rc=rate_calc_per_nic, inc=include, exc=exclude):
                    counters = psutil_bindings.net_io_counters_per_nic(include=inc, exclude=exc)
                    return rc.update(counters)

                entities.append(SystemMultiSensor(
                    mqtt_settings, device,
                    name="Network IO Rates Per NIC",
                    unique_id="network_io_rates_per_nic",
                    fn=_net_io_rates_per_nic,
                    interval=io_interval,
                    icon="mdi:network",
                    units={},
                ))

    # --- Processes ---
    if "processes" in config_dict and config_dict["processes"]:
        for proc_config in config_dict["processes"]:
            proc_name = proc_config["name"]
            proc_id = proc_config.get("id") or proc_name.lower().replace(" ", "_")
            proc_pattern = proc_config["pattern"]
            proc_interval = proc_config.get("polling_interval", DEFAULT_SYSTEM_PROCESS_INTERVAL)

            monitor = psutil_bindings.ProcessMonitor(proc_pattern)

            entities.append(SystemMultiSensor(
                mqtt_settings, device,
                name=f"Process {proc_name}",
                unique_id=f"process_{proc_id}",
                fn=monitor.get_stats,
                interval=proc_interval,
                icon="mdi:application",
                units={
                    "status": None,
                    "cpu_percent": "%",
                    "memory_percent": "%",
                    "memory_rss": "MB",
                    "memory_vms": "MB",
                },
            ))

    logger.info("Created %d system entities", len(entities))
    return entities
