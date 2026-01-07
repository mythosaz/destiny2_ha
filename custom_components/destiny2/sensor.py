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
    SENSOR_CHARACTERS,
    SENSOR_DAILY_RESET,
    SENSOR_GUARDIAN,
    SENSOR_ROTATORS,
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
        Destiny2GuardianSensor(coordinator, entry),
        Destiny2CharactersSensor(coordinator, entry),
        Destiny2RotatorsSensor(coordinator, entry),
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
        membership_id = entry.data.get("membership_id", "unknown")
        self._attr_unique_id = f"destiny2_{membership_id}_{sensor_type}"
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


class Destiny2GuardianSensor(Destiny2SensorBase):
    """Sensor for Guardian profile information."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_GUARDIAN, "Guardian")
        self._attr_icon = "mdi:account"

    @property
    def native_value(self) -> str | None:
        """Return the Bungie name as the state."""
        if self.coordinator.data and "guardian" in self.coordinator.data:
            return self.coordinator.data["guardian"].get("bungie_name", "Unknown")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "guardian" not in self.coordinator.data:
            return {}

        guardian = self.coordinator.data["guardian"]

        return {
            "display_name": guardian.get("display_name"),
            "membership_id": guardian.get("membership_id"),
            "membership_type": guardian.get("membership_type"),
            "membership_type_name": guardian.get("membership_type_name"),
            "first_access": guardian.get("first_access"),
        }


class Destiny2CharactersSensor(Destiny2SensorBase):
    """Sensor for character information including postmaster tracking."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_CHARACTERS, "Characters")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:account-multiple"

    @property
    def native_value(self) -> int | None:
        """Return the number of characters as the state."""
        if self.coordinator.data and "characters" in self.coordinator.data:
            char_data = self.coordinator.data["characters"]
            if char_data:
                return char_data.get("count", 0)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.get("characters") is not None
        )

    @property
    def icon(self) -> str:
        """Return the icon, changing if postmaster is critical."""
        if self.coordinator.data and "characters" in self.coordinator.data:
            char_data = self.coordinator.data["characters"]
            if char_data and char_data.get("postmaster_critical"):
                return "mdi:email-alert"
        return "mdi:account-multiple"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "characters" not in self.coordinator.data:
            return {}

        char_data = self.coordinator.data["characters"]
        if not char_data:
            return {}

        attributes = {
            "postmaster_critical": char_data.get("postmaster_critical", False),
            "characters": [],
        }

        for char in char_data.get("characters", []):
            attributes["characters"].append(
                {
                    "class": char.get("class"),
                    "race": char.get("race"),
                    "gender": char.get("gender"),
                    "light": char.get("light"),
                    "postmaster_count": char.get("postmaster_count"),
                    "last_played": char.get("last_played"),
                }
            )

        return attributes


class Destiny2RotatorsSensor(Destiny2SensorBase):
    """Sensor for featured raid and dungeon rotators."""

    def __init__(self, coordinator: Destiny2Coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, SENSOR_ROTATORS, "Rotators")
        self._attr_icon = "mdi:sword-cross"

    @property
    def native_value(self) -> str:
        """Return a simple state."""
        if self.coordinator.data and "rotators" in self.coordinator.data:
            rotators = self.coordinator.data["rotators"]
            raid_count = len(rotators.get("raids", []))
            dungeon_count = len(rotators.get("dungeons", []))
            other_count = len(rotators.get("other", []))

            if raid_count > 0 or dungeon_count > 0 or other_count > 0:
                return "Available"
        return "None"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if not self.coordinator.data or "rotators" not in self.coordinator.data:
            return {}

        rotators = self.coordinator.data["rotators"]

        attributes = {
            "raids": [],
            "dungeons": [],
            "other": [],
        }

        # Add raid rotators
        for raid in rotators.get("raids", []):
            attributes["raids"].append(
                {
                    "name": raid.get("name"),
                    "activity": raid.get("activity"),
                    "has_master": raid.get("has_master", False),
                    "end_date": raid.get("end_date"),
                }
            )

        # Add dungeon rotators
        for dungeon in rotators.get("dungeons", []):
            attributes["dungeons"].append(
                {
                    "name": dungeon.get("name"),
                    "activity": dungeon.get("activity"),
                    "has_master": dungeon.get("has_master", False),
                    "end_date": dungeon.get("end_date"),
                }
            )

        # Add other rotators
        for other in rotators.get("other", []):
            attributes["other"].append(
                {
                    "name": other.get("name"),
                    "activity": other.get("activity"),
                    "has_master": other.get("has_master", False),
                    "end_date": other.get("end_date"),
                }
            )

        return attributes
