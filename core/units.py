"""Unit resolver — derives measurement units from sensor key names.

Used by SystemMultiSensor as a fallback when explicit units aren't provided.
Handles flattened keys like "sda:read_bytes" by resolving the suffix part.
"""

# Suffix → unit mapping (checked in order, first match wins)
_SUFFIX_RULES: list[tuple[str, str]] = [
    # Percentages
    ("_percentage", "%"),
    ("_percent", "%"),
    ("percent", "%"),
    # Byte rates
    ("_byte_rate", "B/s"),
    ("bytes_sent", "MB/s"),
    ("bytes_recv", "MB/s"),
    # Rates (ops)
    ("_rate", "ops/s"),
    ("packets_sent", "packets/s"),
    ("packets_recv", "packets/s"),
    ("errin", "errors/s"),
    ("errout", "errors/s"),
    ("dropin", "drops/s"),
    ("dropout", "drops/s"),
    # Bytes (absolute)
    ("_bytes", "B"),
    # Counts
    ("_count", "ops"),
    # Time
    ("_time", "s"),
    ("busy_time", "s"),
]

# Exact key → unit (highest priority)
_EXACT_UNITS: dict[str, str] = {
    "percent": "%",
    "total": None,  # ambiguous without context
}


def resolve_unit(key: str, context: str | None = None) -> str | None:
    """Derive unit from a sensor key name.

    Args:
        key: The sensor key, possibly flattened (e.g., "sda:read_bytes").
        context: Optional context hint (e.g., "temperature", "fan", "network_rate").

    Returns:
        Unit string or None if no match.
    """
    # For flattened keys like "sda:read_bytes", resolve the suffix part
    if ":" in key:
        _, suffix = key.rsplit(":", 1)
        return resolve_unit(suffix, context)

    # Context-based overrides
    if context == "temperature":
        return "°C"
    if context == "fan":
        return "RPM"
    if context == "frequency":
        return "GHz"
    if context == "cpu_percent":
        return "%"

    # Exact match
    if key in _EXACT_UNITS:
        return _EXACT_UNITS[key]

    # Suffix matching
    for suffix, unit in _SUFFIX_RULES:
        if key == suffix or key.endswith(suffix):
            return unit

    return None
