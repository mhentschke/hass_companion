import psutil

def parse_cpu_freq(percpu = True):
    """Parse CPU frequency information."""
    freqs = psutil.cpu_freq(percpu=percpu)
    if percpu:
        result = []
        for core in freqs:
            result.append(core.current)
    else:
        result = freqs.current
    return result