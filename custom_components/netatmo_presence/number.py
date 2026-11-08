"""Floodlight intensity for Netatmo Presence.

Unlike the light entity, this changes the intensity without changing the mode,
so it also sets how bright the light is in auto mode.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import FloodlightEntity, async_add_camera_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the intensity sliders."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: [PresenceIntensity(coordinator, cam_id, "intensity")],
    )


class PresenceIntensity(FloodlightEntity, NumberEntity):
    """Floodlight intensity in percent."""

    _attr_translation_key = "intensity"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        intensity = self.floodlight.get("intensity")
        return None if intensity is None else float(intensity)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_set({"intensity": int(round(value))})
