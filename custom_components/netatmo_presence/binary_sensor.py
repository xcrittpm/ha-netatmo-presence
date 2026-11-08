"""Motion sensors for Netatmo Presence: any motion, person, animal, vehicle."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import SENSOR_KINDS
from .coordinator import PresenceCoordinator
from .entity import PresenceEntity, async_add_camera_entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the motion sensors."""
    coordinator = entry.runtime_data
    async_add_camera_entities(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: [PresenceMotion(coordinator, cam_id, kind) for kind in SENSOR_KINDS],
    )


class PresenceMotion(PresenceEntity, BinarySensorEntity):
    """On for a few seconds after Netatmo reports a detection."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: PresenceCoordinator, camera_id: str, kind: str) -> None:
        super().__init__(coordinator, camera_id, f"motion_{kind}")
        self._kind = kind
        self._attr_translation_key = kind
        self._unsub_expire: CALLBACK_TYPE | None = None

    @property
    def available(self) -> bool:
        # Motion arrives by webhook, so it works even if a poll failed.
        return self._camera_id in self.coordinator.cameras

    def _seconds_left(self) -> float:
        last = self.coordinator.motion.get(self._camera_id, {}).get(self._kind)
        if last is None:
            return 0
        return self.coordinator.motion_timeout - (time.monotonic() - last)

    @property
    def is_on(self) -> bool:
        return self._seconds_left() > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last: datetime | None = self.coordinator.last_detection.get(self._camera_id, {}).get(
            self._kind
        )
        return {"last_detection": last.isoformat() if last else None}

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule_expiry()
        super()._handle_coordinator_update()

    @callback
    def _schedule_expiry(self) -> None:
        if self._unsub_expire:
            self._unsub_expire()
            self._unsub_expire = None
        left = self._seconds_left()
        if left > 0:
            self._unsub_expire = async_call_later(self.hass, left + 0.1, self._expire)

    @callback
    def _expire(self, _now: datetime) -> None:
        self._unsub_expire = None
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_expire:
            self._unsub_expire()
            self._unsub_expire = None
        await super().async_will_remove_from_hass()
