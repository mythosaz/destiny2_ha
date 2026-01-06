"""Sensor platform for Destiny 2."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    SENSOR_DAILY_RESET,
    SENSOR_SEASON_END,
    SENSOR_VAULT_COUNT,
    SENSOR_WEEKLY_RESET,
)
from .coordinator import Destiny2Coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Destiny 2 sensors from a config entry."""
    coordinator: Destiny2Coordinator = hass.data[DOMAIN][entry.entry_id]

    # Create all sensors
    sensors = [
        Destiny2WeeklyResetSensor(coordinator, entry),
        Destiny2DailyResetSensor(coordinator, entry),
        Destiny2SeasonEndSensor(coordinator, entry),
        Destiny2VaultCountSensor(coordinator, entry),
    ]

    async_add_entities(sensors)


class Destiny2SensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Destiny 2 sensors."""

    def __init__(
        self,
        coordinator: Destiny2Coordinator,
        entry: ConfigEntry,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = f"Destiny 2 {name}"
        self._attr_unique_id = f"destiny2_{sensor_type}"
        self._entry = entry


class Destiny2WeeklyResetSensor(Destiny2SensorBase):
    """Sensor for weekly reset time."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_WEEKLY_RESET, "Weekly Reset")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-week"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "weekly_reset" in self.coordinator.data:
            return self.coordinator.data["weekly_reset"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "weekly_reset" not in self.coordinator.data:
            return {}

        reset_time = self.coordinator.data["weekly_reset"]
        now = datetime.now(reset_time.tzinfo)
        time_until = reset_time - now

        return {
            "days_until": time_until.days,
            "hours_until": time_until.seconds // 3600,
            "reset_day": "Tuesday",
            "reset_time_utc": "17:00",
        }


class Destiny2DailyResetSensor(Destiny2SensorBase):
    """Sensor for daily reset time."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_DAILY_RESET, "Daily Reset")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-today"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "daily_reset" in self.coordinator.data:
            return self.coordinator.data["daily_reset"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "daily_reset" not in self.coordinator.data:
            return {}

        reset_time = self.coordinator.data["daily_reset"]
        now = datetime.now(reset_time.tzinfo)
        time_until = reset_time - now

        return {
            "hours_until": time_until.seconds // 3600,
            "minutes_until": (time_until.seconds % 3600) // 60,
            "reset_time_utc": "17:00",
        }


class Destiny2SeasonEndSensor(Destiny2SensorBase):
    """Sensor for season end date."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_SEASON_END, "Season End")
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:calendar-end"

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "season_end" in self.coordinator.data:
            return self.coordinator.data["season_end"]
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("season_end") is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or not self.coordinator.data.get("season_end"):
            return {}

        season_end = self.coordinator.data["season_end"]
        now = datetime.now(season_end.tzinfo)
        time_until = season_end - now

        return {
            "days_until": time_until.days,
        }


class Destiny2VaultCountSensor(Destiny2SensorBase):
    """Sensor for vault item count."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_VAULT_COUNT, "Vault Count")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:treasure-chest"
        self._attr_native_unit_of_measurement = "items"

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if self.coordinator.data and "vault_count" in self.coordinator.data:
            return self.coordinator.data["vault_count"]
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("vault_count") is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or self.coordinator.data.get("vault_count") is None:
            return {}

        count = self.coordinator.data["vault_count"]
        max_vault = 600  # Destiny 2 vault capacity

        return {
            "max_capacity": max_vault,
            "remaining_space": max_vault - count,
            "percent_full": round((count / max_vault) * 100, 1),
        }
