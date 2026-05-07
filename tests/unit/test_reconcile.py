"""Unit tests for EntityReconciler.diff() — verifies add/remove/update/unchanged detection."""

from core.config import (
    AppConfig,
    ButtonConfig,
    EntitiesConfig,
    HassConfig,
    MQTTConfig,
    SensorConfig,
    SwitchConfig,
    SystemConfig,
    SystemCpuConfig,
    SystemCpuPercentConfig,
    SystemMemoryConfig,
)
from core.reconcile import EntityReconciler


def _make_config(
    sensors=None, binary_sensors=None, switches=None, buttons=None, selects=None, system=None
) -> AppConfig:
    """Helper to build an AppConfig with given entity lists."""
    return AppConfig(
        mqtt=MQTTConfig(),
        hass=HassConfig(device_name="Test", device_id="test"),
        entities=EntitiesConfig(
            sensors=sensors or [],
            binary_sensors=binary_sensors or [],
            switches=switches or [],
            buttons=buttons or [],
            selects=selects or [],
            system=system,
        ),
    )


class TestEntityReconcilerRegularEntities:
    def test_no_changes(self):
        """Identical configs produce no diff."""
        sensor = SensorConfig(name="temp", command="echo 42", polling_interval=10)
        old = _make_config(sensors=[sensor])
        new = _make_config(sensors=[sensor])

        diff = EntityReconciler.diff(old, new)

        assert diff.to_add == []
        assert diff.to_remove == []
        assert diff.to_update == []
        assert "temp" in diff.unchanged

    def test_entity_added(self):
        """New entity in new config appears in to_add."""
        old = _make_config(sensors=[])
        sensor = SensorConfig(name="temp", command="echo 42", polling_interval=10)
        new = _make_config(sensors=[sensor])

        diff = EntityReconciler.diff(old, new)

        assert len(diff.to_add) == 1
        assert diff.to_add[0][0] == "sensor"
        assert diff.to_add[0][1] == "temp"
        assert diff.to_remove == []
        assert diff.to_update == []

    def test_entity_removed(self):
        """Entity missing from new config appears in to_remove."""
        sensor = SensorConfig(name="temp", command="echo 42", polling_interval=10)
        old = _make_config(sensors=[sensor])
        new = _make_config(sensors=[])

        diff = EntityReconciler.diff(old, new)

        assert diff.to_add == []
        assert len(diff.to_remove) == 1
        assert diff.to_remove[0] == ("sensor", "temp")
        assert diff.to_update == []

    def test_entity_updated(self):
        """Entity with changed field appears in to_update."""
        old_sensor = SensorConfig(name="temp", command="echo 42", polling_interval=10)
        new_sensor = SensorConfig(name="temp", command="echo 99", polling_interval=10)
        old = _make_config(sensors=[old_sensor])
        new = _make_config(sensors=[new_sensor])

        diff = EntityReconciler.diff(old, new)

        assert diff.to_add == []
        assert diff.to_remove == []
        assert len(diff.to_update) == 1
        assert diff.to_update[0][0] == "sensor"
        assert diff.to_update[0][1] == "temp"

    def test_entity_with_explicit_id(self):
        """Entity identity uses explicit id field over name."""
        old_sensor = SensorConfig(name="Temperature", id="temp_1", command="echo 42", polling_interval=10)
        new_sensor = SensorConfig(name="Temperature", id="temp_1", command="echo 99", polling_interval=10)
        old = _make_config(sensors=[old_sensor])
        new = _make_config(sensors=[new_sensor])

        diff = EntityReconciler.diff(old, new)

        assert len(diff.to_update) == 1
        assert diff.to_update[0][1] == "temp_1"

    def test_mixed_changes(self):
        """Multiple entity types with adds, removes, updates, and unchanged."""
        old = _make_config(
            sensors=[SensorConfig(name="keep", command="echo 1", polling_interval=10)],
            buttons=[ButtonConfig(name="old_btn", command="echo press")],
            switches=[
                SwitchConfig(name="sw1", command_on="echo on", command_off="echo off"),
            ],
        )
        new = _make_config(
            sensors=[SensorConfig(name="keep", command="echo 1", polling_interval=10)],
            buttons=[ButtonConfig(name="new_btn", command="echo press")],
            switches=[
                SwitchConfig(name="sw1", command_on="echo ON", command_off="echo off"),
            ],
        )

        diff = EntityReconciler.diff(old, new)

        assert ("button", "new_btn") in [(a[0], a[1]) for a in diff.to_add]
        assert ("button", "old_btn") in diff.to_remove
        assert ("switch", "sw1") in [(u[0], u[1]) for u in diff.to_update]
        assert "keep" in diff.unchanged


class TestEntityReconcilerSystemEntities:
    def test_system_section_added(self):
        """New system section appears in to_add."""
        old = _make_config(system=None)
        new = _make_config(
            system=SystemConfig(cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True)))
        )

        diff = EntityReconciler.diff(old, new)

        assert ("system", "system_cpu") in [(a[0], a[1]) for a in diff.to_add]

    def test_system_section_removed(self):
        """Removed system section appears in to_remove."""
        old = _make_config(
            system=SystemConfig(cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True)))
        )
        new = _make_config(system=SystemConfig())

        diff = EntityReconciler.diff(old, new)

        assert ("system", "system_cpu") in diff.to_remove

    def test_system_section_updated(self):
        """Changed system section appears in to_update."""
        old = _make_config(
            system=SystemConfig(cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True, per_cpu=False)))
        )
        new = _make_config(
            system=SystemConfig(cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True, per_cpu=True)))
        )

        diff = EntityReconciler.diff(old, new)

        assert ("system", "system_cpu") in [(u[0], u[1]) for u in diff.to_update]

    def test_system_section_unchanged(self):
        """Identical system section appears in unchanged."""
        cpu = SystemCpuConfig(percent=SystemCpuPercentConfig(total=True))
        old = _make_config(system=SystemConfig(cpu=cpu))
        new = _make_config(system=SystemConfig(cpu=cpu))

        diff = EntityReconciler.diff(old, new)

        assert "system_cpu" in diff.unchanged

    def test_multiple_system_sections(self):
        """Multiple system sections are compared independently."""
        old = _make_config(
            system=SystemConfig(
                cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True)),
                memory=SystemMemoryConfig(virtual={}, swap={}),
            )
        )
        new = _make_config(
            system=SystemConfig(
                cpu=SystemCpuConfig(percent=SystemCpuPercentConfig(total=True)),
                memory=SystemMemoryConfig(virtual={}),
            )
        )

        diff = EntityReconciler.diff(old, new)

        assert "system_cpu" in diff.unchanged
        assert ("system", "system_memory") in [(u[0], u[1]) for u in diff.to_update]
