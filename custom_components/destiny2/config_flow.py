"""Config flow for Destiny 2 integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import http
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import get_url

from .callback import CALLBACK_PATH
from .const import (
    API_BASE_URL,
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
    MEMBERSHIP_TYPES,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

# Redirect URI options
REDIRECT_OPTIONS = {
    "external": "External URL (Internet/Nabu Casa)",
    "internal": "Internal URL (Local Network)",
    "custom": "Custom URL",
}


class OAuth2FlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Destiny 2."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_key: str | None = None
        self._client_id: str | None = None
        self._client_secret: str | None = None
        self._code: str | None = None
        self._redirect_uri: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - collect API credentials."""
        errors = {}

        if user_input is not None:
            self._api_key = user_input[CONF_API_KEY]
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]

            # Get redirect URL based on user selection
            redirect_source = user_input.get("redirect_source", "external")
            base_url = None

            if redirect_source == "external":
                try:
                    base_url = get_url(self.hass, prefer_external=True)
                except Exception:
                    base_url = self.hass.config.external_url
            elif redirect_source == "internal":
                try:
                    base_url = get_url(self.hass, prefer_external=False)
                except Exception:
                    base_url = self.hass.config.internal_url
            elif redirect_source == "custom":
                base_url = user_input.get("custom_redirect_url", "").rstrip("/")
                if not base_url:
                    errors["custom_redirect_url"] = "custom_url_required"

            # Validate base_url
            if not base_url:
                errors["base"] = "no_url_available"

            if errors:
                # Re-show form with errors
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_API_KEY): str,
                            vol.Required(CONF_CLIENT_ID): str,
                            vol.Required(CONF_CLIENT_SECRET): str,
                            vol.Required("redirect_source", default="external"): vol.In(
                                REDIRECT_OPTIONS
                            ),
                            vol.Optional("custom_redirect_url"): str,
                        }
                    ),
                    errors=errors,
                )

            # Use custom callback endpoint
            self._redirect_uri = f"{base_url}{CALLBACK_PATH}"

            # Debug logging
            _LOGGER.debug("Flow ID: %s", self.flow_id)
            _LOGGER.debug("Redirect source: %s", redirect_source)
            _LOGGER.debug("Base URL: %s", base_url)
            _LOGGER.debug("Redirect URI: %s", self._redirect_uri)

            # Build authorization URL with all required params
            # Use flow_id as state - HA uses this to route callbacks
            auth_params = urlencode(
                {
                    "client_id": self._client_id,
                    "response_type": "code",
                    "state": self.flow_id,  # HA uses flow_id to correlate callbacks
                    "redirect_uri": self._redirect_uri,
                },
                quote_via=quote,
            )

            auth_url = f"{OAUTH_AUTHORIZE_URL}?{auth_params}"
            _LOGGER.debug("Final auth URL: %s", auth_url)

            return self.async_external_step(step_id="auth", url=auth_url)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                    vol.Required("redirect_source", default="external"): vol.In(REDIRECT_OPTIONS),
                    vol.Optional("custom_redirect_url"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle external authentication callback."""
        _LOGGER.debug("async_step_auth called with: %s", user_input)

        if user_input is not None and "code" in user_input:
            # Store the code, then signal external step is done
            # HA will automatically call async_step_token next
            self._code = user_input["code"]
            return self.async_external_step_done(next_step_id="token")

        # No code provided
        return self.async_abort(reason="missing_code")

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Exchange authorization code for access token."""
        session = async_get_clientsession(self.hass)

        token_data_payload = {
            "grant_type": "authorization_code",
            "code": self._code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        if self._redirect_uri:
            token_data_payload["redirect_uri"] = self._redirect_uri

        try:
            # Step 1: Exchange code for tokens
            async with session.post(
                OAUTH_TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=token_data_payload,
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    _LOGGER.error("Token exchange failed with status %s: %s", response.status, response_text)
                    return self.async_abort(reason="token_exchange_failed")

                token_data = await response.json()

            # Step 2: Get membership info
            membership_id = None
            membership_type = -1
            bungie_name = "Unknown"
            bungie_name_code = 0
            display_name = "Unknown"
            first_access = None

            async with session.get(
                f"{API_BASE_URL}/User/GetMembershipsForCurrentUser/",
                headers={
                    "X-API-Key": self._api_key,
                    "Authorization": f"Bearer {token_data.get('access_token')}",
                },
            ) as response:
                if response.status == 200:
                    membership_data = await response.json()
                    _LOGGER.debug("Membership data: %s", membership_data)

                    if "Response" in membership_data:
                        resp = membership_data["Response"]
                        memberships = resp.get("destinyMemberships", [])
                        primary_id = resp.get("primaryMembershipId")

                        # Get Bungie.net user info
                        bungie_user = resp.get("bungieNetUser", {})
                        first_access = bungie_user.get("firstAccess")

                        # Find primary membership or use first available
                        for m in memberships:
                            if primary_id and m.get("membershipId") == primary_id:
                                membership_id = m.get("membershipId")
                                membership_type = m.get("membershipType")
                                display_name = m.get("displayName", "Unknown")
                                bungie_name = m.get("bungieGlobalDisplayName", display_name)
                                bungie_name_code = m.get("bungieGlobalDisplayNameCode", 0)
                                _LOGGER.info("Using primary membership: type=%s, id=%s", membership_type, membership_id)
                                break

                        # Fallback to first membership if no primary
                        if not membership_id and memberships:
                            m = memberships[0]
                            membership_id = m.get("membershipId")
                            membership_type = m.get("membershipType")
                            display_name = m.get("displayName", "Unknown")
                            bungie_name = m.get("bungieGlobalDisplayName", display_name)
                            bungie_name_code = m.get("bungieGlobalDisplayNameCode", 0)
                            _LOGGER.info("Using first membership: type=%s, id=%s", membership_type, membership_id)
                else:
                    _LOGGER.warning("Failed to get memberships: %s", response.status)
                    membership_id = token_data.get("membership_id")

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed during token/membership exchange: %s", err)
            return self.async_abort(reason="connection_error")

        # Build full Bungie name with code
        full_bungie_name = f"{bungie_name}#{bungie_name_code}" if bungie_name_code else bungie_name

        # Store all credentials, tokens, and profile info
        data = {
            CONF_API_KEY: self._api_key,
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in", 3600),
            "membership_id": membership_id,
            "membership_type": membership_type,
            "membership_type_name": MEMBERSHIP_TYPES.get(membership_type, "Unknown"),
            "bungie_name": full_bungie_name,
            "display_name": display_name,
            "first_access": first_access,
        }

        # Create entry
        await self.async_set_unique_id(f"destiny2_{membership_id or 'unknown'}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=f"Destiny 2 - {full_bungie_name}", data=data)
