"""Network sensors — async ping and DNS entities using subprocess.

These entities don't fit the SystemFetcher pattern (they run external commands
with structured output parsing), so they implement their own async poll loops
while extending CompositeEntity for multi-sensor publishing.
"""

import asyncio
import logging
from typing import Any

from core.config import DNSHostConfig, PingHostConfig
from core.entities.base import CompositeEntity
from core.dns_bindings import parse_dig
from core.ping_bindings import parse_ping

logger = logging.getLogger(__name__)


class PingSensor(CompositeEntity):
    """Async ping entity — publishes RTT and packet loss as separate HA sensors.

    Creates two HA sensors per host:
      - {id}_rtt: round-trip time in milliseconds
      - {id}_packet_loss: packet loss percentage

    Implements availability tracking: marks unavailable after 3 consecutive
    timeouts, marks available again on recovery.
    """

    def __init__(
        self,
        mqtt_settings,
        device,
        *,
        config: PingHostConfig,
        _ha_entities: dict[str, Any] | None = None,
    ):
        host_id = config.id or config.host.replace(".", "_").replace(":", "_")
        super().__init__(
            mqtt_settings,
            device,
            name=f"Ping {config.host}",
            unique_id=f"ping_{host_id}",
            icon="mdi:lan-pending",
            units={"rtt": "ms", "packet_loss": "%"},
        )
        self._config = config
        self._exit = asyncio.Event()
        self._failure_count = 0
        self._failure_threshold = 3
        self._available = True

        if _ha_entities is not None:
            self._ha_entities = _ha_entities
        else:
            self._create_ha_entities({"rtt": 0.0, "packet_loss": 0.0})

    def _create_ha_entities(self, sample_result) -> None:
        """Create RTT and packet_loss HA sensors."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Sensor as HASensor,
            SensorInfo as HASensorInfo,
        )

        for key in sample_result:
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

    async def run(self) -> None:
        """Poll loop: execute ping, parse output, update sensors."""
        while not self._exit.is_set():
            await self._execute_ping()
            try:
                await asyncio.wait_for(self._exit.wait(), timeout=self._config.polling_interval)
            except asyncio.TimeoutError:
                pass  # Normal — time to poll again

    async def _execute_ping(self) -> None:
        """Run ping via asyncio.create_subprocess_exec(), parse RTT + loss."""
        command = ["ping"]
        if self._config.interface:
            command += ["-I", self._config.interface]
        if self._config.size is not None:
            command += ["-s", str(self._config.size)]
        if self._config.timeout:
            command += ["-W", str(int(self._config.timeout))]
        command += ["-c", "1", self._config.host]

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self._config.timeout + 5
            )
            output = stdout.decode()

            try:
                result = parse_ping(output)
            except (AttributeError, IndexError, ValueError):
                # parse_ping can fail on malformed output (e.g. 100% loss format)
                logger.warning("Ping to %s: failed to parse output", self._config.host)
                self._record_failure()
                return

            if "time" in result:
                self._ha_entities["rtt"].set_state(result["time"])
                self._ha_entities["packet_loss"].set_state(result["packet_loss"])
                self._record_success()
            else:
                # Ping ran but no RTT (100% loss)
                self._ha_entities["packet_loss"].set_state(result.get("packet_loss", 100.0))
                self._record_failure()

        except (asyncio.TimeoutError, OSError) as e:
            logger.warning("Ping to %s failed: %s", self._config.host, e)
            self._record_failure()

    def _record_success(self) -> None:
        """Reset failure count and mark available if previously unavailable."""
        self._failure_count = 0
        if not self._available:
            self._available = True
            logger.info("Ping %s is now available", self._config.host)
            if self._ha_entities:
                for entity in self._ha_entities.values():
                    if hasattr(entity, "set_availability"):
                        entity.set_availability(True)

    def _record_failure(self) -> None:
        """Increment failure count and mark unavailable if threshold reached."""
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold and self._available:
            self._available = False
            logger.warning(
                "Ping %s is now unavailable after %d consecutive failures",
                self._config.host,
                self._failure_count,
            )
            if self._ha_entities:
                for entity in self._ha_entities.values():
                    if hasattr(entity, "set_availability"):
                        entity.set_availability(False)

    def stop(self) -> None:
        """Signal the poll loop to exit."""
        self._exit.set()


class DNSSensor(CompositeEntity):
    """Async DNS lookup entity — publishes resolution time as an HA sensor.

    Creates one HA sensor per host: {id}_resolution_time (ms).

    Implements availability tracking: marks unavailable after 3 consecutive
    failures, marks available again on recovery.
    """

    def __init__(
        self,
        mqtt_settings,
        device,
        *,
        config: DNSHostConfig,
        _ha_entities: dict[str, Any] | None = None,
    ):
        host_id = config.id or config.host.replace(".", "_").replace(":", "_")
        super().__init__(
            mqtt_settings,
            device,
            name=f"DNS {config.host}",
            unique_id=f"dns_{host_id}",
            icon="mdi:dns",
            units={"resolution_time": "ms"},
        )
        self._config = config
        self._exit = asyncio.Event()
        self._failure_count = 0
        self._failure_threshold = 3
        self._available = True

        if _ha_entities is not None:
            self._ha_entities = _ha_entities
        else:
            self._create_ha_entities({"resolution_time": 0.0})

    def _create_ha_entities(self, sample_result) -> None:
        """Create resolution_time HA sensor."""
        from ha_mqtt_discoverable import Settings as HASettings
        from ha_mqtt_discoverable.sensors import (
            Sensor as HASensor,
            SensorInfo as HASensorInfo,
        )

        for key in sample_result:
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

    async def run(self) -> None:
        """Poll loop: execute dig, parse output, update sensor."""
        while not self._exit.is_set():
            await self._execute_dig()
            try:
                await asyncio.wait_for(self._exit.wait(), timeout=self._config.polling_interval)
            except asyncio.TimeoutError:
                pass  # Normal — time to poll again

    async def _execute_dig(self) -> None:
        """Run dig via asyncio.create_subprocess_exec(), parse resolution time."""
        command = ["dig", self._config.host]

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
            output = stdout.decode()

            try:
                result = parse_dig(output)
            except (AttributeError, IndexError, ValueError):
                logger.warning("DNS lookup for %s: failed to parse output", self._config.host)
                self._record_failure()
                return

            if "resolution_time" in result:
                self._ha_entities["resolution_time"].set_state(result["resolution_time"])
                self._record_success()
            else:
                self._record_failure()

        except (asyncio.TimeoutError, OSError) as e:
            logger.warning("DNS lookup for %s failed: %s", self._config.host, e)
            self._record_failure()

    def _record_success(self) -> None:
        """Reset failure count and mark available if previously unavailable."""
        self._failure_count = 0
        if not self._available:
            self._available = True
            logger.info("DNS %s is now available", self._config.host)
            if self._ha_entities:
                for entity in self._ha_entities.values():
                    if hasattr(entity, "set_availability"):
                        entity.set_availability(True)

    def _record_failure(self) -> None:
        """Increment failure count and mark unavailable if threshold reached."""
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold and self._available:
            self._available = False
            logger.warning(
                "DNS %s is now unavailable after %d consecutive failures",
                self._config.host,
                self._failure_count,
            )
            if self._ha_entities:
                for entity in self._ha_entities.values():
                    if hasattr(entity, "set_availability"):
                        entity.set_availability(False)

    def stop(self) -> None:
        """Signal the poll loop to exit."""
        self._exit.set()
