import psutil
import time
import re
import copy

def cpu_freq(*args, **kwargs):
    """Parse CPU frequency information."""
    freqs = psutil.cpu_freq(*args, **kwargs)
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

def disk_io_counters(perdisk = False, flatten = True):
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
            

disk_io_last_counters = disk_io_counters()
disk_io_last_time = time.time()
disk_io_last_counters_perdisk = disk_io_counters(perdisk = True, flatten = False)
disk_io_last_time_perdisk = time.time()

def disk_io_rates(perdisk = False, include = None, exclude = None):
    global disk_io_last_counters, disk_io_last_time, disk_io_last_counters_perdisk, disk_io_last_time_perdisk
    disk_info = disk_io_counters(perdisk=perdisk, flatten = False)
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
        for key in metrics:
            if key in disk_info:
                disk_rates[key_map[key]] = (disk_info[key] - disk_io_last_counters[key]) / (current_time - disk_io_last_time)
        disk_rates = dict_unit_convert(disk_rates, 100, ["read_percentage", "write_percentage", "busy_percentage"])
        disk_io_last_counters = disk_info
        disk_io_last_time = current_time
    else:
        for drive in disk_info.keys():
            disk_rates[drive] = {}
            for key in metrics:
                if key in disk_info[drive]:
                    disk_rates[drive][key_map[key]] = (disk_info[drive][key] - disk_io_last_counters_perdisk[drive][key]) / (current_time - disk_io_last_time_perdisk)
            disk_rates[drive] = dict_unit_convert(disk_rates[drive], 100, ["read_percentage", "write_percentage", "busy_percentage"])
        disk_io_last_counters_perdisk = disk_info
        disk_io_last_time_perdisk = current_time

    return flatten_dict(dict_round(disk_rates, precision=2))

def net_io_counters():
    """Parse network IO counters."""
    net_info = psutil.net_io_counters()._asdict()
    conversion_keys = ["bytes_sent", "bytes_recv"]
    conversion_factor = 1/(1024 ** 2)  # Convert bytes to MB
    net_info = dict_unit_convert(net_info, conversion_factor, conversion_keys)
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
    result = dict_round(result, precision=1)
    return result

def sensors_fans():
    """Parse sensor fans."""
    sensors = psutil.sensors_fans()
    result = {}
    for key, value in sensors.items():
        result[key] = {}
        for entry in value:
            result[key + ":" + entry.label] = entry.current
    result = dict_round(result, precision=1)
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
    stats = {"status": "Not Running", "cpu_percent": 0.0, "memory_percent": 0.0, "memory_rss": 0.0, "memory_vms": 0.0}
    if proc is not None:
        proc = processes_cache[pattern]
        with proc.oneshot():
            stats["status"] = proc.status().capitalize()
            stats["cpu_percent"] = proc.cpu_percent()
            stats["memory_percent"] = proc.memory_percent()
            stats["memory_rss"] = proc.memory_info().rss / (1024 ** 2)  # Convert bytes to MB
            stats["memory_vms"] = proc.memory_info().vms / (1024 ** 2)  # Convert bytes to MB
        


