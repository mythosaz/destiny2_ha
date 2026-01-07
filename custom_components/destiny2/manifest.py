"""Manifest lookup helper for Destiny 2."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE_URL

_LOGGER = logging.getLogger(__name__)


class ManifestCache:
    """Cache for Destiny 2 manifest lookups."""

    def __init__(self, hass: HomeAssistant, api_key: str) -> None:
        """Initialize the manifest cache."""
        self._hass = hass
        self._api_key = api_key
        self._cache: dict[str, dict[str, Any]] = {
            "DestinyMilestoneDefinition": {},
            "DestinyActivityDefinition": {},
            "DestinyClassDefinition": {},
            "DestinyInventoryItemDefinition": {},
            "DestinyRaceDefinition": {},
            "DestinyGenderDefinition": {},
        }

    async def get_definition(
        self, definition_type: str, hash_id: int | str
    ) -> dict[str, Any] | None:
        """Get a definition from cache or fetch from API.

        Args:
            definition_type: e.g., "DestinyMilestoneDefinition", "DestinyActivityDefinition"
            hash_id: The hash to look up

        Returns:
            The definition dict or None if not found
        """
        hash_str = str(hash_id)

        # Check cache first
        if definition_type in self._cache:
            if hash_str in self._cache[definition_type]:
                return self._cache[definition_type][hash_str]
        else:
            self._cache[definition_type] = {}

        # Fetch from API
        session = async_get_clientsession(self._hass)
        url = f"{API_BASE_URL}/Destiny2/Manifest/{definition_type}/{hash_str}/"

        try:
            async with session.get(
                url,
                headers={"X-API-Key": self._api_key},
            ) as response:
                if response.status != 200:
                    _LOGGER.debug(
                        "Manifest lookup failed for %s/%s: %s",
                        definition_type,
                        hash_str,
                        response.status,
                    )
                    return None

                data = await response.json()

                if "Response" in data:
                    definition = data["Response"]
                    self._cache[definition_type][hash_str] = definition
                    return definition

                return None

        except aiohttp.ClientError as err:
            _LOGGER.error("Manifest fetch error for %s/%s: %s", definition_type, hash_str, err)
            return None

    async def get_milestone_name(self, hash_id: int | str) -> str:
        """Get milestone display name."""
        definition = await self.get_definition("DestinyMilestoneDefinition", hash_id)
        if definition and "displayProperties" in definition:
            return definition["displayProperties"].get("name", f"Unknown ({hash_id})")
        return f"Unknown ({hash_id})"

    async def get_activity_name(self, hash_id: int | str) -> str:
        """Get activity display name."""
        definition = await self.get_definition("DestinyActivityDefinition", hash_id)
        if definition and "displayProperties" in definition:
            return definition["displayProperties"].get("name", f"Unknown ({hash_id})")
        return f"Unknown ({hash_id})"

    async def get_class_name(self, hash_id: int | str) -> str:
        """Get class display name."""
        definition = await self.get_definition("DestinyClassDefinition", hash_id)
        if definition and "displayProperties" in definition:
            return definition["displayProperties"].get("name", f"Unknown ({hash_id})")
        return f"Unknown ({hash_id})"

    def get_cache_stats(self) -> dict[str, int]:
        """Return count of cached items per type."""
        return {k: len(v) for k, v in self._cache.items()}
