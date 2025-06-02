import psutil

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
