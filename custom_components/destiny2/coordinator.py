"""Data update coordinator for Destiny 2."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_MILESTONES,
    BUCKET_POSTMASTER,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
    OAUTH_TOKEN_URL,
    UPDATE_INTERVAL,
)
from .manifest import ManifestCache

_LOGGER = logging.getLogger(__name__)


class Destiny2Coordinator(DataUpdateCoordinator):
    """Coordinator to manage Destiny 2 data updates."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, update_interval: timedelta | None = None
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval or UPDATE_INTERVAL,
        )
        self.entry = entry
        self._api_key = entry.data[CONF_API_KEY]
        self._access_token = entry.data.get("access_token")
        self._refresh_token = entry.data.get("refresh_token")
        self._token_expires_at = None
        self.manifest = ManifestCache(hass, entry.data[CONF_API_KEY])

        # Calculate token expiration time
        if "expires_in" in entry.data:
            self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=entry.data["expires_in"]
            )

    async def async_refresh_token_if_needed(self) -> None:
        """Refresh the access token if it's expired or about to expire."""
        if self._token_expires_at is None:
            return

        # Refresh if token expires in less than 5 minutes
        if datetime.now(timezone.utc) + timedelta(minutes=5) < self._token_expires_at:
            return

        _LOGGER.debug("Refreshing access token")
        session = async_get_clientsession(self.hass)

        try:
            async with session.post(
                OAUTH_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self.entry.data[CONF_CLIENT_ID],
                    "client_secret": self.entry.data[CONF_CLIENT_SECRET],
                },
            ) as response:
                if response.status != 200:
                    _LOGGER.error("Token refresh failed: %s", await response.text())
                    raise UpdateFailed("Failed to refresh access token")

                token_data = await response.json()

                # Update tokens
                self._access_token = token_data.get("access_token")
                self._refresh_token = token_data.get("refresh_token", self._refresh_token)
                self._token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=token_data.get("expires_in", 3600)
                )

                # Update config entry
                self.hass.config_entries.async_update_entry(
                    self.entry,
                    data={
                        **self.entry.data,
                        "access_token": self._access_token,
                        "refresh_token": self._refresh_token,
                        "expires_in": token_data.get("expires_in", 3600),
                    },
                )

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to refresh token: %s", err)
            raise UpdateFailed(f"Token refresh error: {err}") from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Bungie API."""
        await self.async_refresh_token_if_needed()

        data = {}

        # Calculated locally
        data["weekly_reset"] = self._calculate_next_weekly_reset()
        data["daily_reset"] = self._calculate_next_daily_reset()

        # Guardian info from stored config
        data["guardian"] = {
            "bungie_name": self.entry.data.get("bungie_name", "Unknown"),
            "display_name": self.entry.data.get("display_name", "Unknown"),
            "membership_id": self.entry.data.get("membership_id"),
            "membership_type": self.entry.data.get("membership_type"),
            "membership_type_name": self.entry.data.get("membership_type_name", "Unknown"),
            "first_access": self.entry.data.get("first_access"),
        }

        # Fetch from API
        try:
            milestones_data = await self._fetch_milestones()
            data["season_end"] = milestones_data.get("season_end")
            data["rotators"] = milestones_data.get("rotators", {})

            data["vault_count"] = await self._fetch_vault_count()
            data["characters"] = await self._fetch_characters()
        except Exception as err:
            _LOGGER.error("Error fetching Destiny 2 data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        return data

    def _calculate_next_weekly_reset(self) -> datetime:
        """Calculate the next weekly reset time (Tuesday 17:00 UTC)."""
        now = datetime.now(timezone.utc)
        # Find next Tuesday
        days_ahead = 1 - now.weekday()  # Tuesday is 1
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        next_reset = now + timedelta(days=days_ahead)
        next_reset = next_reset.replace(hour=17, minute=0, second=0, microsecond=0)

        # If we're past Tuesday 17:00, go to next week
        if next_reset <= now:
            next_reset += timedelta(days=7)

        return next_reset

    def _calculate_next_daily_reset(self) -> datetime:
        """Calculate the next daily reset time (17:00 UTC)."""
        now = datetime.now(timezone.utc)
        next_reset = now.replace(hour=17, minute=0, second=0, microsecond=0)

        # If we're past today's reset, go to tomorrow
        if next_reset <= now:
            next_reset += timedelta(days=1)

        return next_reset

    async def _fetch_milestones(self) -> dict[str, Any]:
        """Fetch milestones and decode rotators."""
        session = async_get_clientsession(self.hass)
        result = {"season_end": None, "rotators": {"raids": [], "dungeons": [], "other": []}}

        try:
            async with session.get(
                f"{API_BASE_URL}{API_MILESTONES}",
                headers={
                    "X-API-Key": self._api_key,
                    "Authorization": f"Bearer {self._access_token}",
                },
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch milestones: %s", response.status)
                    return result

                data = await response.json()

                if "Response" not in data:
                    return result

                milestones = data["Response"]
                latest_end_date = None

                _LOGGER.debug("=== BEGIN MILESTONE DECODE ===")

                for milestone_hash, milestone_data in milestones.items():
                    milestone_name = await self.manifest.get_milestone_name(milestone_hash)

                    # Get first activity name
                    activity_name = None
                    has_master = False
                    if "activities" in milestone_data:
                        for activity in milestone_data["activities"]:
                            if "activityHash" in activity:
                                act_name = await self.manifest.get_activity_name(activity["activityHash"])
                                if activity_name is None:
                                    activity_name = act_name
                                if "Master" in act_name:
                                    has_master = True

                    end_date_str = milestone_data.get("endDate")

                    _LOGGER.debug(
                        "Milestone: %s | Activity: %s | Master: %s | Ends: %s",
                        milestone_name,
                        activity_name or "none",
                        has_master,
                        end_date_str or "no end date",
                    )

                    # Categorize by name patterns
                    name_lower = milestone_name.lower() if milestone_name else ""

                    # Known raid names
                    raid_keywords = [
                        "last wish",
                        "garden of salvation",
                        "deep stone crypt",
                        "vault of glass",
                        "vow of the disciple",
                        "king's fall",
                        "root of nightmares",
                        "crota's end",
                        "salvation's edge",
                    ]

                    # Known dungeon names
                    dungeon_keywords = [
                        "shattered throne",
                        "pit of heresy",
                        "prophecy",
                        "grasp of avarice",
                        "duality",
                        "spire of the watcher",
                        "ghosts of the deep",
                        "warlord's ruin",
                        "vesper's host",
                        "desert perpetual",
                    ]

                    entry = {
                        "name": milestone_name,
                        "activity": activity_name,
                        "has_master": has_master,
                        "end_date": end_date_str,
                    }

                    if any(kw in name_lower for kw in raid_keywords):
                        result["rotators"]["raids"].append(entry)
                    elif any(kw in name_lower for kw in dungeon_keywords):
                        result["rotators"]["dungeons"].append(entry)
                    elif activity_name and end_date_str:
                        result["rotators"]["other"].append(entry)

                    # Track season end
                    if end_date_str:
                        try:
                            end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                            if latest_end_date is None or end_date > latest_end_date:
                                latest_end_date = end_date
                        except (ValueError, AttributeError):
                            continue

                _LOGGER.debug("=== END MILESTONE DECODE ===")
                _LOGGER.debug("Manifest cache stats: %s", self.manifest.get_cache_stats())
                _LOGGER.debug(
                    "Rotators found - Raids: %d, Dungeons: %d, Other: %d",
                    len(result["rotators"]["raids"]),
                    len(result["rotators"]["dungeons"]),
                    len(result["rotators"]["other"]),
                )

                result["season_end"] = latest_end_date
                return result

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch milestones: %s", err)
            return result

    async def _fetch_vault_count(self) -> int | None:
        """Fetch vault item count from Bungie API."""
        membership_id = self.entry.data.get("membership_id")
        membership_type = self.entry.data.get("membership_type", -1)  # -1 auto-resolves cross-save

        if not membership_id:
            _LOGGER.warning("No membership ID available")
            return None

        session = async_get_clientsession(self.hass)

        try:
            async with session.get(
                f"{API_BASE_URL}/Destiny2/{membership_type}/Profile/{membership_id}/?components=102",
                headers={
                    "X-API-Key": self._api_key,
                    "Authorization": f"Bearer {self._access_token}",
                },
            ) as response:
                if response.status == 500:
                    _LOGGER.warning(
                        "Bungie API returned 500 for vault - will retry next cycle. "
                        "Preserving last known value."
                    )
                    return self.data.get("vault_count") if self.data else None

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.warning(
                        "Failed to fetch vault count: %s - %s", response.status, response_text[:200]
                    )
                    return None

                data = await response.json()

                if "Response" in data and "profileInventory" in data["Response"]:
                    profile_inv = data["Response"]["profileInventory"]
                    if "data" in profile_inv and "items" in profile_inv["data"]:
                        items = profile_inv["data"]["items"]
                        return len(items) if items else 0

                _LOGGER.warning("Unexpected vault response structure")
                return None

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch vault count: %s", err)
            return None

    async def _fetch_characters(self) -> dict[str, Any] | None:
        """Fetch character info including postmaster counts."""
        membership_id = self.entry.data.get("membership_id")
        membership_type = self.entry.data.get("membership_type", -1)

        if not membership_id:
            _LOGGER.warning("No membership ID available for characters")
            return None

        session = async_get_clientsession(self.hass)

        try:
            # Components: 200 = Characters, 201 = CharacterInventories
            async with session.get(
                f"{API_BASE_URL}/Destiny2/{membership_type}/Profile/{membership_id}/?components=200,201",
                headers={
                    "X-API-Key": self._api_key,
                    "Authorization": f"Bearer {self._access_token}",
                },
            ) as response:
                if response.status == 500:
                    _LOGGER.warning(
                        "Bungie API returned 500 for characters - will retry next cycle. "
                        "Preserving last known value."
                    )
                    return self.data.get("characters") if self.data else None

                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.warning(
                        "Failed to fetch characters: %s - %s", response.status, response_text[:200]
                    )
                    return None

                data = await response.json()

                if "Response" not in data:
                    _LOGGER.warning("Unexpected characters response structure")
                    return None

                response_data = data["Response"]
                characters_data = response_data.get("characters", {}).get("data", {})
                inventories_data = response_data.get("characterInventories", {}).get("data", {})

                characters = []
                postmaster_critical = False

                _LOGGER.debug("=== BEGIN CHARACTER DECODE ===")

                for char_id, char_info in characters_data.items():
                    # Decode class, race, gender
                    class_name = await self.manifest.get_class_name(char_info.get("classHash"))
                    race_name = await self._get_race_name(char_info.get("raceHash"))
                    gender_name = await self._get_gender_name(char_info.get("genderHash"))

                    # Count postmaster items
                    postmaster_count = 0
                    if char_id in inventories_data:
                        items = inventories_data[char_id].get("items", [])
                        postmaster_count = sum(
                            1 for item in items if item.get("bucketHash") == BUCKET_POSTMASTER
                        )

                    # Flag critical if >= 18 items
                    if postmaster_count >= 18:
                        postmaster_critical = True

                    light_level = char_info.get("light", 0)
                    emblem_hash = char_info.get("emblemHash")
                    last_played = char_info.get("dateLastPlayed")

                    _LOGGER.debug(
                        "Character: %s %s %s | Light: %s | Postmaster: %s/21 | Last played: %s",
                        race_name,
                        gender_name,
                        class_name,
                        light_level,
                        postmaster_count,
                        last_played or "never",
                    )

                    characters.append(
                        {
                            "character_id": char_id,
                            "class": class_name,
                            "race": race_name,
                            "gender": gender_name,
                            "light": light_level,
                            "emblem_hash": emblem_hash,
                            "last_played": last_played,
                            "postmaster_count": postmaster_count,
                        }
                    )

                # Sort by last_played descending (most recent first)
                characters.sort(
                    key=lambda c: c.get("last_played") or "", reverse=True
                )

                _LOGGER.debug("=== END CHARACTER DECODE ===")
                _LOGGER.debug("Characters found: %d", len(characters))
                _LOGGER.debug("Postmaster critical: %s", postmaster_critical)

                return {
                    "count": len(characters),
                    "characters": characters,
                    "postmaster_critical": postmaster_critical,
                }

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch characters: %s", err)
            return None

    async def _get_race_name(self, hash_id: int | str | None) -> str:
        """Get race display name from hash."""
        if hash_id is None:
            return "Unknown"

        definition = await self.manifest.get_definition("DestinyRaceDefinition", hash_id)
        if definition and "displayProperties" in definition:
            return definition["displayProperties"].get("name", f"Unknown ({hash_id})")
        return f"Unknown ({hash_id})"

    async def _get_gender_name(self, hash_id: int | str | None) -> str:
        """Get gender display name from hash."""
        if hash_id is None:
            return "Unknown"

        definition = await self.manifest.get_definition("DestinyGenderDefinition", hash_id)
        if definition and "displayProperties" in definition:
            return definition["displayProperties"].get("name", f"Unknown ({hash_id})")
        return f"Unknown ({hash_id})"
