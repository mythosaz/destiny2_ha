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
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


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

            # Generate redirect URI using Home Assistant's external URL
            try:
                base_url = get_url(self.hass, prefer_external=True)
            except Exception:
                # Fallback to external_url if get_url fails
                base_url = self.hass.config.external_url or "http://homeassistant.local:8123"

            # Use custom callback endpoint instead of HA's built-in OAuth endpoint
            self._redirect_uri = f"{base_url}{CALLBACK_PATH}"

            # Debug: Check what flow_id actually is
            _LOGGER.debug("Flow ID type: %s", type(self.flow_id))
            _LOGGER.debug("Flow ID value: %s", self.flow_id)
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
                }
            ),
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle external authentication callback."""
        _LOGGER.debug("async_step_auth called with: %s", user_input)

        if user_input is None:
            # Waiting for callback - tell HA we're ready for external step completion
            return self.async_external_step_done(next_step_id="auth")

        # Callback view has provided the authorization code
        if "code" not in user_input:
            return self.async_abort(reason="missing_code")

        self._code = user_input["code"]

        # Exchange code for tokens
        return await self.async_step_token()

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Exchange authorization code for access token."""
        session = async_get_clientsession(self.hass)

        # Prepare token exchange data
        token_data_payload = {
            "grant_type": "authorization_code",
            "code": self._code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        # Include redirect_uri if it was set
        if self._redirect_uri:
            token_data_payload["redirect_uri"] = self._redirect_uri

        try:
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

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to exchange token: %s", err)
            return self.async_abort(reason="connection_error")

        # Store all credentials and tokens
        data = {
            CONF_API_KEY: self._api_key,
            CONF_CLIENT_ID: self._client_id,
            CONF_CLIENT_SECRET: self._client_secret,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in", 3600),
            "membership_id": token_data.get("membership_id"),
        }

        # Create entry
        await self.async_set_unique_id(f"destiny2_{data.get('membership_id', 'unknown')}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title="Destiny 2", data=data)
