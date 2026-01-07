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
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    API_BASE_URL,
    API_MILESTONES,
    DOMAIN,
    OAUTH_TOKEN_URL,
    UPDATE_INTERVAL,
)
from .manifest import ManifestCache

_LOGGER = logging.getLogger(__name__)


class Destiny2Coordinator(DataUpdateCoordinator):
    """Coordinator to manage Destiny 2 data updates."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
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
        # Refresh token if needed
        await self.async_refresh_token_if_needed()

        data = {}

        # Calculate reset times (these don't require API calls)
        data["weekly_reset"] = self._calculate_next_weekly_reset()
        data["daily_reset"] = self._calculate_next_daily_reset()

        # Fetch season end and vault count from API
        try:
            data["season_end"] = await self._fetch_season_end()
            data["vault_count"] = await self._fetch_vault_count()
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

    async def _fetch_season_end(self) -> datetime | None:
        """Fetch season end date from Bungie API and log decoded milestones."""
        session = async_get_clientsession(self.hass)

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
                    return None

                data = await response.json()

                if "Response" not in data:
                    _LOGGER.warning("No Response in milestones data")
                    return None

                milestones = data["Response"]
                latest_end_date = None

                # Decode and log all milestones
                _LOGGER.debug("=== BEGIN MILESTONE DECODE ===")

                for milestone_hash, milestone_data in milestones.items():
                    # Get milestone type name
                    milestone_name = await self.manifest.get_milestone_name(milestone_hash)

                    # Get activity names if present
                    activity_names = []
                    if "activities" in milestone_data:
                        for activity in milestone_data["activities"]:
                            if "activityHash" in activity:
                                activity_name = await self.manifest.get_activity_name(
                                    activity["activityHash"]
                                )
                                activity_names.append(activity_name)

                    # Log the decoded milestone
                    end_date_str = milestone_data.get("endDate", "no end date")
                    _LOGGER.info(
                        "Milestone: %s | Activities: %s | Ends: %s",
                        milestone_name,
                        ", ".join(activity_names) if activity_names else "none",
                        end_date_str,
                    )

                    # Track latest end date for season
                    if "endDate" in milestone_data:
                        try:
                            end_date = datetime.fromisoformat(
                                milestone_data["endDate"].replace("Z", "+00:00")
                            )
                            if latest_end_date is None or end_date > latest_end_date:
                                latest_end_date = end_date
                        except (ValueError, AttributeError):
                            continue

                _LOGGER.debug("=== END MILESTONE DECODE ===")
                _LOGGER.debug("Manifest cache stats: %s", self.manifest.get_cache_stats())

                return latest_end_date

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch season end: %s", err)
            return None

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
