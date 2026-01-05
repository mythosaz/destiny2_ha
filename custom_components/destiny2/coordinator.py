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
        """Fetch season end date from Bungie API."""
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

                # Parse season end from milestones
                # This is a simplified example - actual parsing may vary
                if "Response" in data:
                    # Look for season-related milestone
                    # The actual structure depends on Bungie's API response
                    # For now, return None as placeholder
                    _LOGGER.debug("Milestones data: %s", data)
                    return None

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch season end: %s", err)
            return None

    async def _fetch_vault_count(self) -> int | None:
        """Fetch vault item count from Bungie API."""
        membership_id = self.entry.data.get("membership_id")
        if not membership_id:
            _LOGGER.warning("No membership ID available")
            return None

        session = async_get_clientsession(self.hass)

        # We need to determine membership type (1=Xbox, 2=PSN, 3=Steam, etc.)
        # For now, we'll try to fetch the profile
        # Component 102 is ProfileInventories (vault)

        try:
            # This is a simplified version - you'd need to get the actual
            # membership type from the initial OAuth response
            membership_type = 3  # Assuming Steam for now

            async with session.get(
                f"{API_BASE_URL}/Destiny2/{membership_type}/Profile/{membership_id}/?components=102",
                headers={
                    "X-API-Key": self._api_key,
                    "Authorization": f"Bearer {self._access_token}",
                },
            ) as response:
                if response.status != 200:
                    _LOGGER.warning("Failed to fetch vault count: %s", response.status)
                    return None

                data = await response.json()

                # Parse vault count
                if "Response" in data and "profileInventory" in data["Response"]:
                    items = data["Response"]["profileInventory"]["data"]["items"]
                    return len(items) if items else 0

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to fetch vault count: %s", err)
            return None
