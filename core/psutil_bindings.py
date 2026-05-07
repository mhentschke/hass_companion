import psutil
import time
import re
import copy
from typing import Any

def cpu_freq(*args, **kwargs):
    """Parse CPU frequency information.

    Guards against None return on Apple Silicon (macOS) where
    cpu_freq(percpu=True) may return None.
    """
    freqs = psutil.cpu_freq(*args, **kwargs)
    if freqs is None:
        if kwargs.get("percpu", False):
            return []
        return 0.0
    if kwargs.get("percpu", False):
        result = []
        for core in freqs:
            result.append(round(core.current / 1000.0, 2))
    else:
        result = round(freqs.current / 1000.0, 2)
    return result

def virtual_memory():
    """Parse virtual memory information."""
    mem_info = psutil.virtual_memory()._asdict()
    conversion_keys = ["total", "available", "used", "free", "active", "inactive", "buffers", "cached", "shared", "slab", "wired"]
    conversion_factor = 1/(1024 ** 2)  # Convert bytes to MB
    mem_info = dict_unit_convert(mem_info, conversion_factor, conversion_keys)
    mem_info = dict_round(mem_info, conversion_keys, 1)
    return mem_info

def swap_memory():
    """Parse swap memory information."""
    swap_info = psutil.swap_memory()._asdict()
    conversion_keys = ["total", "used", "free"]
    conversion_factor = 1/(1024 ** 2)  # Convert bytes to MB
    swap_info = dict_unit_convert(swap_info, conversion_factor, conversion_keys)
    swap_info = dict_round(swap_info, conversion_keys, 1)
    return swap_info

def disk_usage(path):
    """Parse disk usage information."""
    disk_info = psutil.disk_usage(path)._asdict()
    conversion_keys = ["total", "used", "free"]
    conversion_factor = 1/(1024 ** 3)  # Convert bytes to GB
    disk_info = dict_unit_convert(disk_info, conversion_factor, conversion_keys)
    disk_info = dict_round(disk_info, conversion_keys, 1)
    return disk_info

def disk_io_counters(perdisk = False, flatten = True, include = [], exclude = []):
    """Parse disk IO counters."""
    disk_info = psutil.disk_io_counters(perdisk = perdisk)#._asdict()
    conversion_keys = ["read_count", "write_count", "read_bytes", "write_bytes"]
    conversion_factor = 1/(1024 ** 3)  # Convert bytes to GB)

    conversion_keys_time = ["read_time", "write_time", "busy_time"]
    conversion_factor_time = 1/1000  # Convert ms to s
    
    if not perdisk:
        disk_info = disk_info._asdict()
        disk_info = dict_unit_convert(disk_info, conversion_factor, conversion_keys)
        disk_info = dict_unit_convert(disk_info, conversion_factor_time, conversion_keys_time)
        disk_info = dict_round(disk_info, conversion_keys, 1)
    else:
        disk_info = filter_dict(disk_info, include, exclude)
        for drive in disk_info.keys():
            disk_info[drive] = dict_unit_convert(disk_info[drive]._asdict(), conversion_factor, conversion_keys)
            disk_info[drive] = dict_unit_convert(disk_info[drive], conversion_factor_time, conversion_keys_time)
            disk_info[drive] = dict_round(disk_info[drive], conversion_keys, 1)
    if flatten:
        disk_info = flatten_dict(disk_info)
    return disk_info

def dict_unit_convert(d, factor, keys = None):
    if keys is None:
        keys = d.keys()
    for key in keys:
        if key in d:
            d[key] *= factor
    return d

def dict_round(d, keys = None, precision = 2):
    if keys is None:
        keys = d.keys()
    for key in keys:
        if key in d:
            if isinstance(d[key], dict):
                d[key] = dict_round(d[key], precision = precision)
            elif isinstance(d[key], float):
                d[key] = round(d[key], precision)
    return d

def flatten_dict(d, separator = ":"):
    keys = copy.deepcopy(list(d.keys()))
    for key in keys:
        if isinstance(d[key], dict):
            for subkey in d[key].keys():
                d[f"{key}{separator}{subkey}"] = d[key][subkey]
            # remove the key
            del d[key]
    return d

def filter_dict(d, include = [], exclude = []):
    result = {}
    if exclude == [] and include == []:
        return d
    elif include == []:
        for pattern in exclude:
            # regex match
            if not "^" in pattern:
                pattern = "^" + pattern
            if not "$" in pattern:
                pattern += "$"
            matcher = re.compile(pattern)
            if isinstance(pattern, str):
                original_keys = copy.deepcopy(list(d.keys()))
                for k in original_keys:
                    if not matcher.match(k):
                        result[k] = d[k]
    else:

        for pattern in include:
            # regex match
            if isinstance(pattern, str):
                if not "^" in pattern:
                    pattern = "^" + pattern
                if not "$" in pattern:
                    pattern += "$"
                matcher = re.compile(pattern)
                original_keys = copy.deepcopy(list(d.keys()))
                for k in original_keys:
                    if matcher.match(k):
                        result[k] = d[k]
    return result


disk_io_last_counters = None
disk_io_last_time = None
disk_io_last_counters_perdisk = None
disk_io_last_time_perdisk = None           



def disk_io_rates(perdisk = False, include = None, exclude = None):
    global disk_io_last_counters, disk_io_last_time, disk_io_last_counters_perdisk, disk_io_last_time_perdisk
    disk_info = disk_io_counters(perdisk=perdisk, flatten = False, include = include, exclude = exclude)
    key_map = {
        "read_count": "read_rate",
        "write_count": "write_rate",
        "read_bytes": "read_byte_rate",
        "write_bytes": "write_byte_rate",
        "read_time": "read_percentage",
        "write_time": "write_percentage",
        "busy_time": "busy_percentage",
    }
    # calculate rates
    disk_rates = {}
    current_time = time.time()
    metrics = ["read_count", "write_count", "read_bytes", "write_bytes", "read_time", "write_time", "busy_time"]
    if not perdisk:
        if not disk_io_last_counters:
            disk_io_last_counters = disk_info
            disk_io_last_time = current_time-1

        for key in metrics:
            if key in disk_info:
                disk_rates[key_map[key]] = (disk_info[key] - disk_io_last_counters[key]) / (current_time - disk_io_last_time)
        disk_rates = dict_unit_convert(disk_rates, 100, ["read_percentage", "write_percentage", "busy_percentage"])
        disk_io_last_counters = disk_info
        disk_io_last_time = current_time
    else:
        if not disk_io_last_counters_perdisk:
            disk_io_last_counters_perdisk = disk_info
            disk_io_last_time_perdisk = current_time-1

        for drive in disk_info.keys():
            disk_rates[drive] = {}
            for key in metrics:
                if key in disk_info[drive]:
                    disk_rates[drive][key_map[key]] = (disk_info[drive][key] - disk_io_last_counters_perdisk[drive][key]) / (current_time - disk_io_last_time_perdisk)
            disk_rates[drive] = dict_unit_convert(disk_rates[drive], 100, ["read_percentage", "write_percentage", "busy_percentage"])
        disk_io_last_counters_perdisk = disk_info
        disk_io_last_time_perdisk = current_time

    return flatten_dict(dict_round(disk_rates, precision=2))

def net_io_counters_total() -> dict[str, float]:
    """Return aggregate network IO counters (bytes in MB, rest raw).

    Keys: bytes_sent, bytes_recv, packets_sent, packets_recv, errin, errout, dropin, dropout
    """
    net_info = psutil.net_io_counters()._asdict()
    conversion_keys = ["bytes_sent", "bytes_recv"]
    conversion_factor = 1 / (1024 ** 2)  # Convert bytes to MB
    net_info = dict_unit_convert(net_info, conversion_factor, conversion_keys)
    return net_info


def net_io_counters_per_nic(include: list[str] | None = None, exclude: list[str] | None = None) -> dict[str, float]:
    """Return per-NIC network IO counters, flattened with 'nic:metric' keys.

    Applies include/exclude regex filtering to NIC names via filter_dict().
    Keys per NIC: bytes_sent, bytes_recv, packets_sent, packets_recv, errin, errout, dropin, dropout
    """
    raw = psutil.net_io_counters(pernic=True)
    # Convert named tuples to dicts
    per_nic: dict[str, dict[str, float]] = {}
    for nic_name, counters in raw.items():
        per_nic[nic_name] = counters._asdict()

    # Apply NIC filtering
    per_nic = filter_dict(per_nic, include=include or [], exclude=exclude or [])

    # Convert bytes to MB for each NIC
    conversion_keys = ["bytes_sent", "bytes_recv"]
    conversion_factor = 1 / (1024 ** 2)
    for nic_name in per_nic:
        per_nic[nic_name] = dict_unit_convert(per_nic[nic_name], conversion_factor, conversion_keys)

    return flatten_dict(per_nic)

def sensors_temperatures():
    """Parse sensor temperatures.

    Returns empty dict on macOS where sensors_temperatures() returns {}.
    """
    sensors = psutil.sensors_temperatures()
    if not sensors:
        return {}
    result = {}
    for key, value in sensors.items():
        result[key] = {}
        for entry in value:
            result[key + ":" + entry.label] = entry.current
    result = dict_round(result, precision=1)
    return result

def sensors_fans():
    """Parse sensor fans.

    Returns empty dict on macOS where sensors_fans() returns {}.
    """
    sensors = psutil.sensors_fans()
    if not sensors:
        return {}
    result = {}
    for key, value in sensors.items():
        result[key] = {}
        for entry in value:
            result[key + ":" + entry.label] = entry.current
    result = dict_round(result, precision=1)
    return result

class ProcessMonitor:
    """Encapsulates process lookup and caching for a single regex pattern.

    Each instance monitors one process pattern. Caches the psutil.Process
    reference and re-scans on NoSuchProcess or when the process is not found.
    """

    def __init__(self, pattern: str):
        self._pattern = pattern
        self._regex = re.compile(pattern)
        self._cached_process: "psutil.Process | None" = None

    def _find_process(self) -> "psutil.Process | None":
        """Scan running processes for one matching the regex pattern."""
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if self._regex.match(proc.info['name']):
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def get_stats(self) -> dict[str, Any]:
        """Return process stats dict with status, cpu_percent, memory_percent, memory_rss, memory_vms.

        Returns "Not Running" state with zero metrics if process is not found.
        Handles NoSuchProcess by clearing cache and returning "Not Running".
        """
        not_running = {
            "status": "Not Running",
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_rss": 0.0,
            "memory_vms": 0.0,
        }

        # Try cached process first
        if self._cached_process is not None:
            try:
                with self._cached_process.oneshot():
                    stats = {
                        "status": self._cached_process.status().capitalize(),
                        "cpu_percent": self._cached_process.cpu_percent(),
                        "memory_percent": round(self._cached_process.memory_percent(), 2),
                        "memory_rss": round(self._cached_process.memory_info().rss / (1024 ** 2), 2),
                        "memory_vms": round(self._cached_process.memory_info().vms / (1024 ** 2), 2),
                    }
                return stats
            except psutil.NoSuchProcess:
                # Process disappeared — clear cache
                self._cached_process = None
                return not_running

        # No cached process — scan for it
        proc = self._find_process()
        if proc is None:
            return not_running

        self._cached_process = proc
        try:
            with proc.oneshot():
                stats = {
                    "status": proc.status().capitalize(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_percent": round(proc.memory_percent(), 2),
                    "memory_rss": round(proc.memory_info().rss / (1024 ** 2), 2),
                    "memory_vms": round(proc.memory_info().vms / (1024 ** 2), 2),
                }
            return stats
        except psutil.NoSuchProcess:
            self._cached_process = None
            return not_running


