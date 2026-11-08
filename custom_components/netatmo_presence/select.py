"""Floodlight mode (on / off / auto) for Netatmo Presence."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODES
from .entity import FloodlightEntity, async_add_camera_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the mode selectors."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: [PresenceFloodlightMode(coordinator, cam_id, "floodlight_mode")],
    )


class PresenceFloodlightMode(FloodlightEntity, SelectEntity):
    """Floodlight mode."""

    _attr_translation_key = "floodlight_mode"
    _attr_options = MODES

    @property
    def current_option(self) -> str | None:
        mode = self.floodlight.get("mode")
        return mode if mode in MODES else None

    async def async_select_option(self, option: str) -> None:
        await self._async_set({"mode": option})
