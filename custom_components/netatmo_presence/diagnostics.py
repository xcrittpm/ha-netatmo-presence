"""Diagnostics with tokens, camera URLs and ids removed."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

TO_REDACT = {
    "token",
    "access_token",
    "refresh_token",
    "webhook_id",
    "cloudhook_url",
    "id",
    "home_id",
    "vpn_url",
    "local_url",
    "base_url",
    "probed_vpn_url",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "webhook_confirmed": coordinator.webhook_confirmed,
        "cameras": [
            {**async_redact_data(asdict(cam), TO_REDACT), "connection": cam.connection}
            for cam in coordinator.cameras.values()
        ],
    }
