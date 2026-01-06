"""OAuth callback handler for Destiny 2."""
import logging

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

_LOGGER = logging.getLogger(__name__)

CALLBACK_PATH = "/api/destiny2/callback"


class Destiny2CallbackView(HomeAssistantView):
    """Handle Destiny 2 OAuth callback."""

    requires_auth = False
    url = CALLBACK_PATH
    name = "api:destiny2:callback"

    async def get(self, request):
        """Handle OAuth callback from Bungie."""
        hass = request.app["hass"]

        code = request.query.get("code")
        state = request.query.get("state")  # This is flow_id

        _LOGGER.debug(
            "OAuth callback received - code: %s, state: %s",
            code[:10] if code else None,
            state,
        )

        if not code or not state:
            return web.Response(
                text="<html><body><h1>Error</h1><p>Missing code or state parameter.</p></body></html>",
                content_type="text/html",
                status=400,
            )

        try:
            # Resume the config flow with the authorization code
            result = await hass.config_entries.flow.async_configure(
                flow_id=state, user_input={"code": code}
            )
            _LOGGER.debug("Flow configure result: %s", result)

            return web.Response(
                text="<html><body><h1>Success!</h1><p>Authorization complete. You can close this window and return to Home Assistant.</p></body></html>",
                content_type="text/html",
            )
        except Exception as err:
            _LOGGER.error("Failed to configure flow: %s", err)
            return web.Response(
                text=f"<html><body><h1>Error</h1><p>Failed to complete authorization: {err}</p></body></html>",
                content_type="text/html",
                status=500,
            )
