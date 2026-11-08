"""Floodlight with brightness for Netatmo Presence."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODE_ON
from .entity import FloodlightEntity, async_add_camera_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the floodlights."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: [PresenceFloodlight(coordinator, cam_id, "floodlight")],
    )


class PresenceFloodlight(FloodlightEntity, LightEntity):
    """The floodlight. On = forced on; off = back to the configured off mode."""

    _attr_translation_key = "floodlight"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool:
        return self.floodlight.get("mode") == MODE_ON

    @property
    def brightness(self) -> int | None:
        intensity = self.floodlight.get("intensity")
        if intensity is None:
            return None
        return round(int(intensity) * 255 / 100)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "mode": self.floodlight.get("mode"),
            "connection": self.camera.connection,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        changes: dict[str, Any] = {"mode": MODE_ON}
        if ATTR_BRIGHTNESS in kwargs:
            changes["intensity"] = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        await self._async_set(changes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set({"mode": self.coordinator.off_mode})
