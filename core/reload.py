"""ReloadManager — orchestrates configuration hot-reload.

Loads new config, diffs against current, stops removed/updated entities,
creates new ones, and reports results. Used by SIGHUP handler and file watcher.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from core.config import AppConfig, ConfigError, load_config
from core.entities.base import BaseEntity
from core.entities.system import create_system_entities
from core.factory import create_entity as factory_create_entity
from core.reconcile import EntityReconciler

logger = logging.getLogger(__name__)


@dataclass
class ReloadResult:
    """Outcome of a reload attempt."""

    success: bool
    new_config: AppConfig | None = None
    new_entities: dict[tuple[str, str], BaseEntity] | None = None
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    restart_reasons: list[str] = field(default_factory=list)
    error: str | None = None


class ReloadManager:
    """Orchestrates config reload: load → validate → diff → apply.

    Stateless per-reload — receives current state, returns new state or error.
    """

    def __init__(
        self,
        config_path: str,
        mqtt_settings: Any,
        ha_device: Any,
        ha_devices: dict[str, Any],
        sub_devices: bool,
        device_name: str,
    ):
        self._config_path = config_path
        self._mqtt_settings = mqtt_settings
        self._ha_device = ha_device
        self._ha_devices = ha_devices
        self._sub_devices = sub_devices
        self._device_name = device_name

    async def reload(
        self,
        current_registry: dict[tuple[str, str], BaseEntity],
        current_config: AppConfig,
    ) -> ReloadResult:
        """Attempt config reload. Returns result with new entities or error.

        On validation failure: returns error result immediately.
        On entity creation failure: rolls back partially created entities, returns error.
        """
        # 1. Load and validate new config
        try:
            new_config = load_config(self._config_path)
        except ConfigError as e:
            error_msg = str(e)
            logger.warning("Reload failed — config validation error: %s", error_msg)
            return ReloadResult(success=False, error=error_msg)

        # 2. Diff old vs new
        diff = EntityReconciler.diff(current_config, new_config)

        # 3. Stop removed entities and publish empty discovery messages
        for entity_type, entity_id in diff.to_remove:
            key = (entity_type, entity_id)
            entity = current_registry.get(key)
            if entity:
                logger.debug("Stopping removed entity: %s/%s", entity_type, entity_id)
                entity.stop()
                self._clear_discovery(entity)

        # 4. Stop updated entities (old instances) and clear their discovery
        for entity_type, entity_id, _new_cfg in diff.to_update:
            key = (entity_type, entity_id)
            entity = current_registry.get(key)
            if entity:
                logger.debug("Stopping updated entity: %s/%s", entity_type, entity_id)
                entity.stop()
                self._clear_discovery(entity)

        # 5. Create new entity instances for added + updated
        created: dict[tuple[str, str], BaseEntity] = {}
        try:
            # Update hass-level settings from new config before creating entities
            self._sub_devices = new_config.hass.sub_devices
            self._device_name = new_config.hass.device_name
            created.update(self._create_entities_from_config(new_config, diff))
        except Exception as e:
            # Roll back: stop any partially created entities
            for entity in created.values():
                entity.stop()
            error_msg = f"Entity creation failed during reload: {e}"
            logger.error(error_msg)
            return ReloadResult(success=False, error=error_msg)

        # 6. Build new registry: unchanged + newly created
        new_registry: dict[tuple[str, str], BaseEntity] = {}

        # Keep unchanged entities
        for key, entity in current_registry.items():
            entity_type, entity_id = key
            if key not in [(t, i) for t, i in diff.to_remove]:
                if key not in [(t, i) for t, i, _ in diff.to_update]:
                    new_registry[key] = entity

        # Add newly created entities
        new_registry.update(created)

        # Build result
        added_names = [eid for _, eid, _ in diff.to_add]
        removed_names = [eid for _, eid in diff.to_remove]
        updated_names = [eid for _, eid, _ in diff.to_update]

        return ReloadResult(
            success=True,
            new_config=new_config,
            new_entities=new_registry,
            added=added_names,
            removed=removed_names,
            updated=updated_names,
            restart_reasons=diff.restart_reasons,
        )

    def _resolve_device(self, entity_config) -> Any:
        """Resolve the HA device for an entity config."""
        device_key = getattr(entity_config, "device", None)
        if device_key and device_key in self._ha_devices:
            return self._ha_devices[device_key]
        return self._ha_device

    def _create_entities_from_config(
        self,
        new_config: AppConfig,
        diff: Any,
    ) -> dict[tuple[str, str], BaseEntity]:
        """Create entity instances for added and updated entries in the diff."""
        created: dict[tuple[str, str], BaseEntity] = {}

        # Collect entity IDs that need creation (added + updated)
        to_create_regular: set[tuple[str, str]] = set()
        for entity_type, entity_id, _ in diff.to_add:
            if entity_type != "system":
                to_create_regular.add((entity_type, entity_id))
        for entity_type, entity_id, _ in diff.to_update:
            if entity_type != "system":
                to_create_regular.add((entity_type, entity_id))

        # Create regular entities from new config
        entity_type_map = {
            "sensor": new_config.entities.sensors,
            "binary_sensor": new_config.entities.binary_sensors,
            "switch": new_config.entities.switches,
            "button": new_config.entities.buttons,
            "select": new_config.entities.selects,
        }

        for entity_type, configs in entity_type_map.items():
            for config in configs:
                entity_id = config.id or config.name
                if (entity_type, entity_id) in to_create_regular:
                    device = self._resolve_device(config)
                    entity = factory_create_entity(entity_type, config, self._mqtt_settings, device)
                    created[(entity_type, entity_id)] = entity

        # Handle system entities — recreate entire sections that changed
        system_sections_to_create: set[str] = set()
        for entity_type, section_id, _ in diff.to_add:
            if entity_type == "system":
                system_sections_to_create.add(section_id)
        for entity_type, section_id, _ in diff.to_update:
            if entity_type == "system":
                system_sections_to_create.add(section_id)

        if system_sections_to_create and new_config.entities.system:
            system_entities = create_system_entities(
                new_config.entities.system,
                self._mqtt_settings,
                self._ha_device,
                sub_devices=new_config.hass.sub_devices,
                device_name=new_config.hass.device_name,
            )
            for entity in system_entities:
                entity_id = getattr(entity, "_base_id", None) or getattr(entity, "_system_id", "unknown")
                # Only include entities from sections that need recreation
                section_prefix = self._get_system_section(entity_id)
                if section_prefix in system_sections_to_create:
                    created[("system", entity_id)] = entity

        return created

    def _get_system_section(self, entity_id: str) -> str:
        """Map a system entity_id back to its section name for filtering."""
        # System entity IDs follow patterns like: cpu_percent, memory_virtual, etc.
        # Section names are: system_cpu, system_memory, system_storage, system_network, system_sensors, system_processes
        section_map = {
            "cpu": "system_cpu",
            "memory": "system_memory",
            "disk": "system_storage",
            "storage": "system_storage",
            "network": "system_network",
            "net": "system_network",
            "temp": "system_sensors",
            "fan": "system_sensors",
            "process": "system_processes",
            "ping": "system_network",
            "dns": "system_network",
        }
        for prefix, section in section_map.items():
            if entity_id.startswith(prefix):
                return section
        return ""

    def _clear_discovery(self, entity: BaseEntity) -> None:
        """Publish empty retained message to entity's discovery topic to deregister from HA.

        Uses the shared MQTT client from mqtt_settings to publish empty payloads.
        """
        try:
            client = self._mqtt_settings.client
            if client is None:
                return

            # For CompositeEntity, clear all sub-entity discovery topics
            if hasattr(entity, "_ha_entities") and entity._ha_entities:
                for ha_entity in entity._ha_entities.values():
                    topic = getattr(ha_entity, "config_topic", None)
                    if topic:
                        client.publish(topic, "", retain=True)
                        logger.debug("Cleared discovery topic: %s", topic)
            # For single Entity, clear its discovery topic
            elif hasattr(entity, "_ha_entity") and entity._ha_entity:
                ha_entity = entity._ha_entity
                topic = getattr(ha_entity, "config_topic", None)
                if topic:
                    client.publish(topic, "", retain=True)
                    logger.debug("Cleared discovery topic: %s", topic)
        except Exception as e:
            logger.warning("Failed to clear discovery for entity: %s", e)
