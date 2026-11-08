"""Night triggers of the floodlight (what turns it on in auto mode)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NIGHT_TRIGGERS
from .coordinator import PresenceCoordinator
from .entity import FloodlightEntity, async_add_camera_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the night trigger switches."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: [
            PresenceNightTrigger(coordinator, cam_id, trigger) for trigger in NIGHT_TRIGGERS
        ],
    )


class PresenceNightTrigger(FloodlightEntity, SwitchEntity):
    """Whether a detection type turns the light on at night in auto mode."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PresenceCoordinator, camera_id: str, trigger: str) -> None:
        super().__init__(coordinator, camera_id, f"night_{trigger}")
        self._trigger = trigger
        self._attr_translation_key = f"night_{trigger}"

    @property
    def is_on(self) -> bool | None:
        night = self.floodlight.get("night")
        if not isinstance(night, dict) or self._trigger not in night:
            return None
        return bool(night[self._trigger])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set({"night": {self._trigger: True}})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set({"night": {self._trigger: False}})
