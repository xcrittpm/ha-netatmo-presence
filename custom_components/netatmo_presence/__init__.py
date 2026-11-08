"""Netatmo Presence: floodlight with brightness and motion sensors."""

from __future__ import annotations

import logging

from aiohttp import web
from yarl import URL

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError

from .api import NetatmoApiError, NetatmoPresenceApi
from .const import (
    CONF_CLOUDHOOK_URL,
    CONF_USE_WEBHOOK,
    CONF_WEBHOOK_ID,
    DEFAULT_USE_WEBHOOK,
    DOMAIN,
)
from .coordinator import PresenceCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def _async_build_api(hass: HomeAssistant, entry: ConfigEntry) -> NetatmoPresenceApi:
    try:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
        )
    except (ValueError, HomeAssistantError) as err:
        raise ConfigEntryNotReady("Netatmo application credentials are not available") from err
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    return NetatmoPresenceApi(session, async_get_clientsession(hass))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Netatmo Presence from a config entry."""
    api = await _async_build_api(hass, entry)
    coordinator = PresenceCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if entry.options.get(CONF_USE_WEBHOOK, DEFAULT_USE_WEBHOOK):
        await _async_setup_webhook(hass, entry, coordinator)

    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Tell Netatmo to stop pushing events and delete the cloudhook."""
    try:
        api = await _async_build_api(hass, entry)
        await api.async_drop_webhook()
    except (ConfigEntryNotReady, NetatmoApiError) as err:
        _LOGGER.debug("Could not drop the Netatmo webhook: %s", err)
    if CONF_CLOUDHOOK_URL in entry.data and "cloud" in hass.config.components:
        from homeassistant.components import cloud  # noqa: PLC0415

        try:
            await cloud.async_delete_cloudhook(hass, entry.data[CONF_WEBHOOK_ID])
        except (HomeAssistantError, cloud.CloudNotAvailable) as err:
            _LOGGER.debug("Could not delete the cloudhook: %s", err)


# ---- Webhook ---------------------------------------------------------------


async def _async_setup_webhook(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PresenceCoordinator
) -> None:
    webhook_id = entry.data[CONF_WEBHOOK_ID]

    async def _handle(
        hass: HomeAssistant, webhook_id: str, request: web.Request
    ) -> web.Response | None:
        try:
            data = await request.json()
        except ValueError:
            return None
        if isinstance(data, dict):
            _LOGGER.debug("Webhook push: %s", data.get("push_type") or data.get("event_type"))
            coordinator.async_handle_webhook(data)
        return None

    webhook.async_register(
        hass, DOMAIN, "Netatmo Presence", webhook_id, _handle, allowed_methods=["POST"]
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))

    url = await _async_get_webhook_url(hass, entry)
    if url is None:
        _LOGGER.warning(
            "No external URL for Home Assistant: motion will be polled instead of pushed"
        )
        return
    parsed = URL(url)
    if parsed.scheme != "https" or parsed.port != 443:
        _LOGGER.warning(
            "Netatmo only pushes events to HTTPS on port 443; motion will be polled instead"
        )
        return
    try:
        await coordinator.api.async_add_webhook(url)
    except NetatmoApiError as err:
        _LOGGER.warning("Could not register the Netatmo webhook (%s); motion will be polled", err)


async def _async_get_webhook_url(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    if "cloud" in hass.config.components:
        from homeassistant.components import cloud  # noqa: PLC0415

        if cloud.async_active_subscription(hass):
            if CONF_CLOUDHOOK_URL not in entry.data:
                try:
                    cloudhook_url = await cloud.async_create_cloudhook(hass, webhook_id)
                except (HomeAssistantError, cloud.CloudNotAvailable) as err:
                    _LOGGER.debug("Could not create a cloudhook: %s", err)
                else:
                    hass.config_entries.async_update_entry(
                        entry, data={**entry.data, CONF_CLOUDHOOK_URL: cloudhook_url}
                    )
            if CONF_CLOUDHOOK_URL in entry.data:
                return entry.data[CONF_CLOUDHOOK_URL]
    try:
        return webhook.async_generate_url(hass, webhook_id, allow_internal=False)
    except NoURLAvailableError:
        return None
