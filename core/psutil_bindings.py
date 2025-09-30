import psutil
import time
import re

def cpu_freq(*args, **kwargs):
    """Parse CPU frequency information."""
    freqs = psutil.cpu_freq(*args, **kwargs)
    if kwargs.get("percpu", False):
        result = []
        for core in freqs:
            result.append(core.current)
    else:
        result = freqs.current
    return result

def virtual_memory():
    """Parse virtual memory information."""
    mem_info = psutil.virtual_memory()._asdict()
    # Convert All units to MB for simplicity
    for key in ["total", "available", "used", "free", "active", "inactive", "buffers", "cached", "shared", "slab", "wired"]:
        if key in mem_info:
            mem_info[key] /= (1024 ** 2)  # Convert bytes to MB
    return mem_info

def swap_memory():
    """Parse swap memory information."""
    swap_info = psutil.swap_memory()._asdict()
    for key in ["total", "free", "used"]:
        if key in swap_info:
            swap_info[key] /= (1024 ** 2)  # Convert bytes to MB
    return swap_info

def disk_usage(path):
    """Parse disk usage information."""
    disk_info = psutil.disk_usage(path)._asdict()
    for key in ["total", "free", "used"]:
        if key in disk_info:
            disk_info[key] /= (1024 ** 3)  # Convert bytes to GB
    return disk_info

def disk_io_counters():
    """Parse disk IO counters."""
    disk_info = psutil.disk_io_counters()._asdict()
    for key in ["read_count", "write_count", "read_bytes", "write_bytes", "read_time", "write_time", "busy_time"]:
        if key in disk_info:
            disk_info[key] /= (1024 ** 3)  # Convert bytes to GB
    return disk_info

disk_io_last_counters = disk_io_counters()
disk_io_last_time = time.time()

def disk_io_rates():
    disk_info = disk_io_counters()
    key_map = {
        "read_count": "read_rate",
        "write_count": "write_rate",
        "read_bytes": "read_byte_rate",
        "write_bytes": "write_byte_rate",
        "read_time": "read_ratio",
        "write_time": "write_ratio",
        "busy_time": "busy_ratio",
    }
    # calculate rates
    disk_rates = {}
    for key in ["read_count", "write_count", "read_bytes", "write_bytes", "read_time", "write_time", "busy_time"]:
        if key in disk_info:
            disk_rates[key_map[key]] = (disk_info[key] - disk_io_last_counters[key]) / (time.time() - disk_io_last_time)
    return disk_rates

def net_io_counters():
    """Parse network IO counters."""
    net_info = psutil.net_io_counters()._asdict()
    for key in ["bytes_sent", "bytes_recv", "packets_sent", "packets_recv", "errin", "errout", "dropin", "dropout"]:
        if key in net_info:
            net_info[key] /= (1024 ** 2)  # Convert bytes to MB
    return net_info
    
net_io_last_counters = net_io_counters()
net_io_last_time = time.time()

def net_io_rates():
    net_info = net_io_counters()
    key_map = {
        "bytes_sent": "bytes_sent_rate",
        "bytes_recv": "bytes_recv_rate",
        "packets_sent": "packets_sent_rate",
        "packets_recv": "packets_recv_rate",
        "errin": "errin_rate",
        "errout": "errout_rate",
        "dropin": "dropin_rate",
        "dropout": "dropout_rate",
    }
    # calculate rates
    net_rates = {}
    for key in ["bytes_sent", "bytes_recv", "packets_sent", "packets_recv", "errin", "errout", "dropin", "dropout"]:
        if key in net_info:
            net_rates[key_map[key]] = (net_info[key] - net_io_last_counters[key]) / (time.time() - net_io_last_time)
    return net_rates

def sensors_temperatures():
    """Parse sensor temperatures."""
    sensors = psutil.sensors_temperatures()
    result = {}
    for key, value in sensors.items():
        result[key] = {}
        for entry in value:
            result[key + ":" + entry.label] = entry.current
    return result

def sensors_fans():
    """Parse sensor fans."""
    sensors = psutil.sensors_fans()
    result = {}
    for key, value in sensors.items():
        result[key] = {}
        for entry in value:
            result[key + ":" + entry.label] = entry.current
    return result

processes_cache = {}
process_re = {}

def get_process(pattern):
    if pattern not in process_re:
        process_re[pattern] = re.compile(pattern)
    if pattern not in processes_cache:
        for proc in psutil.process_iter(['pid', 'name']):
            if process_re[pattern].match(proc.info['name']):
                processes_cache[pattern] = proc
                break
    if pattern in processes_cache:
        return processes_cache[pattern]
    return None

def process_sensors(pattern):
    proc = get_process(pattern)
    stats = {"status": "Not Running", "cpu_percent", 0.0, "memory_percent": 0.0, "memory_rss": 0.0, "memory_vms": 0.0}
    if proc is not None:
        proc = processes_cache[pattern]
        with proc.oneshot():
            stats["status"] = proc.status().capitalize()
            stats["cpu_percent"] = proc.cpu_percent()
            stats["memory_percent"] = proc.memory_percent()
            stats["memory_rss"] = proc.memory_info().rss / (1024 ** 2)  # Convert bytes to MB
            stats["memory_vms"] = proc.memory_info().vms / (1024 ** 2)  # Convert bytes to MB
        


