"""Entity reconciliation — compares two configs to determine add/remove/update.

Used by the ReloadManager to determine what changed between config reloads.
"""

from dataclasses import dataclass, field
from typing import Any

from core.config import AppConfig, SystemConfig


@dataclass
class EntityDiff:
    """Result of comparing two configurations.

    Each entry in to_add/to_remove/to_update is (entity_type, entity_id, config_data).
    unchanged contains entity_ids that did not change.
    restart_reasons lists changes that require a full restart to take effect.
    """

    to_add: list[tuple[str, str, Any]] = field(default_factory=list)
    to_remove: list[tuple[str, str]] = field(default_factory=list)
    to_update: list[tuple[str, str, Any]] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    restart_reasons: list[str] = field(default_factory=list)


def _sanitize_id(name: str) -> str:
    """Derive entity_id from name (matches HA discovery unique_id logic)."""
    return name


def _get_entity_id(config) -> str:
    """Get the identity key for a regular entity config."""
    return config.id or _sanitize_id(config.name)


def _extract_regular_entities(entities_config) -> dict[tuple[str, str], Any]:
    """Extract regular (non-system) entities as {(type, id): config_dump}.

    Returns a dict keyed by (entity_type, entity_id) with the Pydantic
    model_dump() as value for change detection.
    """
    result: dict[tuple[str, str], Any] = {}

    entity_types = [
        ("sensor", entities_config.sensors),
        ("binary_sensor", entities_config.binary_sensors),
        ("switch", entities_config.switches),
        ("button", entities_config.buttons),
        ("select", entities_config.selects),
    ]

    for entity_type, configs in entity_types:
        for config in configs:
            entity_id = _get_entity_id(config)
            key = (entity_type, entity_id)
            result[key] = config.model_dump()

    return result


def _extract_system_sections(system_config: SystemConfig | None) -> dict[str, Any]:
    """Extract system entity sections as {section_name: serialized_config}.

    System entities are compared at the section level — if any field within
    a section changes, the entire section's entities are recreated.
    """
    if system_config is None:
        return {}

    sections: dict[str, Any] = {}

    if system_config.cpu is not None:
        sections["system_cpu"] = system_config.cpu.model_dump()

    if system_config.memory is not None:
        sections["system_memory"] = system_config.memory.model_dump()

    if system_config.storage is not None:
        sections["system_storage"] = system_config.storage.model_dump()

    if system_config.network is not None:
        sections["system_network"] = system_config.network.model_dump()

    if system_config.sensors is not None:
        sections["system_sensors"] = system_config.sensors.model_dump()

    if system_config.processes:
        sections["system_processes"] = [p.model_dump() for p in system_config.processes]

    return sections


def _detect_device_only_changes(
    old_config: dict, new_config: dict
) -> bool:
    """Check if the only difference between two entity configs is the device key."""
    old_copy = {k: v for k, v in old_config.items() if k != "device"}
    new_copy = {k: v for k, v in new_config.items() if k != "device"}
    return old_copy == new_copy and old_config.get("device") != new_config.get("device")


class EntityReconciler:
    """Compares two AppConfig instances and produces an EntityDiff."""

    @staticmethod
    def diff(old_config: AppConfig, new_config: AppConfig) -> EntityDiff:
        """Compare old and new configs, return what needs to change.

        Regular entities are compared individually by (type, id) key.
        System entities are compared at the section level.
        Changes that only affect device assignment (sub_devices, device_name,
        entity device key) are flagged as restart_reasons rather than updates.
        """
        result = EntityDiff()

        # --- Detect hass-level changes that affect device assignment ---
        sub_devices_changed = old_config.hass.sub_devices != new_config.hass.sub_devices
        device_name_changed = old_config.hass.device_name != new_config.hass.device_name

        if sub_devices_changed:
            result.restart_reasons.append(
                f"hass.sub_devices changed ({old_config.hass.sub_devices} → {new_config.hass.sub_devices})"
            )
        if device_name_changed:
            result.restart_reasons.append(
                f"hass.device_name changed ('{old_config.hass.device_name}' → '{new_config.hass.device_name}')"
            )

        # --- Regular entities ---
        old_entities = _extract_regular_entities(old_config.entities)
        new_entities = _extract_regular_entities(new_config.entities)

        old_keys = set(old_entities.keys())
        new_keys = set(new_entities.keys())

        # Added
        for key in new_keys - old_keys:
            entity_type, entity_id = key
            result.to_add.append((entity_type, entity_id, new_entities[key]))

        # Removed
        for key in old_keys - new_keys:
            entity_type, entity_id = key
            result.to_remove.append((entity_type, entity_id))

        # Possibly updated
        for key in old_keys & new_keys:
            entity_type, entity_id = key
            if old_entities[key] != new_entities[key]:
                # Check if only the device key changed
                if _detect_device_only_changes(old_entities[key], new_entities[key]):
                    result.restart_reasons.append(
                        f"{entity_type}/{entity_id}: device changed"
                    )
                else:
                    result.to_update.append((entity_type, entity_id, new_entities[key]))
            else:
                result.unchanged.append(entity_id)

        # --- System entities (section-level comparison) ---
        old_sections = _extract_system_sections(old_config.entities.system)
        new_sections = _extract_system_sections(new_config.entities.system)

        old_section_keys = set(old_sections.keys())
        new_section_keys = set(new_sections.keys())

        # Added sections
        for section in new_section_keys - old_section_keys:
            result.to_add.append(("system", section, new_sections[section]))

        # Removed sections
        for section in old_section_keys - new_section_keys:
            result.to_remove.append(("system", section))

        # Possibly updated sections
        for section in old_section_keys & new_section_keys:
            if old_sections[section] != new_sections[section]:
                # Real config change — recreate
                result.to_update.append(("system", section, new_sections[section]))
            else:
                result.unchanged.append(section)

        return result
