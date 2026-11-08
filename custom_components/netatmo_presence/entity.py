"""Base entity for Netatmo Presence."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PresenceCamera, PresenceCoordinator


class PresenceEntity(CoordinatorEntity[PresenceCoordinator]):
    """An entity that belongs to one Presence camera."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PresenceCoordinator, camera_id: str, key: str) -> None:
        super().__init__(coordinator)
        self._camera_id = camera_id
        self._attr_unique_id = f"{camera_id}_{key}"
        cam = coordinator.cameras[camera_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, camera_id)},
            manufacturer="Netatmo",
            model="Presence (NOC)",
            name=cam.name,
            sw_version=str(cam.firmware) if cam.firmware else None,
        )

    @property
    def camera(self) -> PresenceCamera:
        """The camera state."""
        return self.coordinator.cameras[self._camera_id]


class FloodlightEntity(PresenceEntity):
    """An entity that needs the floodlight config read from the camera."""

    @property
    def available(self) -> bool:
        return super().available and self.camera.config is not None

    @property
    def floodlight(self) -> dict[str, Any]:
        """The camera's floodlight config."""
        return self.camera.config or {}

    async def _async_set(self, changes: dict[str, Any]) -> None:
        await self.coordinator.async_set_floodlight(self._camera_id, changes)


def async_add_camera_entities(
    entry: ConfigEntry,
    coordinator: PresenceCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[str], Iterable[Entity]],
) -> None:
    """Add entities for every camera, including cameras found later."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [cam_id for cam_id in coordinator.cameras if cam_id not in known]
        if not new:
            return
        known.update(new)
        async_add_entities([entity for cam_id in new for entity in factory(cam_id)])

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
