"""Config flow for Netatmo Presence (OAuth2 sign-in plus options)."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import API_BASE
from .const import (
    CONF_MOTION_TIMEOUT,
    CONF_OFF_MODE,
    CONF_SCAN_INTERVAL,
    CONF_USE_WEBHOOK,
    CONF_WEBHOOK_ID,
    DEFAULT_MOTION_TIMEOUT,
    DEFAULT_OFF_MODE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USE_WEBHOOK,
    DOMAIN,
    MODE_AUTO,
    MODE_OFF,
    MODULE_TYPE_PRESENCE,
    SCOPES,
)


class OAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Sign in to Netatmo."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(__name__)

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        return {"scope": " ".join(SCOPES)}

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The token stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Check the account has a Presence and create the entry."""
        websession = async_get_clientsession(self.hass)
        try:
            async with websession.get(
                f"{API_BASE}/homesdata",
                headers={"Authorization": f"Bearer {data['token']['access_token']}"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                resp.raise_for_status()
                body = (await resp.json(content_type=None)).get("body", {})
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return self.async_abort(reason="cannot_connect")

        homes = body.get("homes") or []
        has_presence = any(
            module.get("type") == MODULE_TYPE_PRESENCE
            for home in homes
            for module in home.get("modules", [])
        )
        if not has_presence:
            return self.async_abort(reason="no_cameras")

        # Hash the account id so it is not stored in clear.
        account = (body.get("user") or {}).get("id") or homes[0].get("id")
        await self.async_set_unique_id(hashlib.sha256(str(account).encode()).hexdigest()[:16])

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )

        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Netatmo Presence",
            data={**data, CONF_WEBHOOK_ID: webhook.async_generate_id()},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PresenceOptionsFlow()


class PresenceOptionsFlow(OptionsFlow):
    """Options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_OFF_MODE: user_input[CONF_OFF_MODE],
                    CONF_MOTION_TIMEOUT: int(user_input[CONF_MOTION_TIMEOUT]),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_USE_WEBHOOK: user_input[CONF_USE_WEBHOOK],
                }
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_OFF_MODE): SelectSelector(
                    SelectSelectorConfig(
                        options=[MODE_AUTO, MODE_OFF],
                        translation_key="off_mode",
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_MOTION_TIMEOUT): NumberSelector(
                    NumberSelectorConfig(
                        min=5, max=600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(CONF_SCAN_INTERVAL): NumberSelector(
                    NumberSelectorConfig(
                        min=30, max=600, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX
                    )
                ),
                vol.Required(CONF_USE_WEBHOOK): BooleanSelector(),
            }
        )
        current = {
            CONF_OFF_MODE: DEFAULT_OFF_MODE,
            CONF_MOTION_TIMEOUT: DEFAULT_MOTION_TIMEOUT,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_USE_WEBHOOK: DEFAULT_USE_WEBHOOK,
            **self.config_entry.options,
        }
        return self.async_show_form(
            step_id="init", data_schema=self.add_suggested_values_to_schema(schema, current)
        )
