"""Polling, local camera access and motion tracking for Netatmo Presence."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    MOVEMENT,
    NetatmoApiError,
    NetatmoAuthError,
    NetatmoPresenceApi,
    detections_from_event,
    detections_from_webhook,
    webhook_camera_id,
    webhook_event_type,
)
from .const import (
    CONF_MOTION_TIMEOUT,
    CONF_OFF_MODE,
    CONF_SCAN_INTERVAL,
    DEFAULT_MOTION_TIMEOUT,
    DEFAULT_OFF_MODE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_DETECTION,
    HOMES_REFRESH_SECONDS,
    MODULE_TYPE_PRESENCE,
    MOTION_ANY,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PresenceCamera:
    """State of one Presence camera."""

    id: str
    name: str
    home_id: str
    firmware: int | None = None
    monitoring: str | None = None
    cloud_floodlight: str | None = None
    vpn_url: str | None = None
    local_url: str | None = None
    base_url: str | None = None
    probed_vpn_url: str | None = None
    config: dict[str, Any] | None = None
    reachable: bool = False

    @property
    def connection(self) -> str:
        """How we talk to the camera: local, relay or none."""
        if not self.base_url:
            return "none"
        return "local" if self.base_url == self.local_url else "relay"


class PresenceCoordinator(DataUpdateCoordinator[dict[str, PresenceCamera]]):
    """Keeps camera state and floodlight config up to date."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: NetatmoPresenceApi) -> None:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.cameras: dict[str, PresenceCamera] = {}
        self.home_ids: set[str] = set()
        # True once Netatmo confirmed the webhook; then event polling stops.
        self.webhook_confirmed = False
        # camera id -> sensor kind -> time.monotonic() of the last detection
        self.motion: defaultdict[str, dict[str, float]] = defaultdict(dict)
        self.last_detection: defaultdict[str, dict[str, datetime]] = defaultdict(dict)
        self._event_baseline: dict[str, int] = {}
        self._homes_refreshed = 0.0

    @property
    def motion_timeout(self) -> int:
        """Seconds a motion sensor stays on after a detection."""
        return int(self.config_entry.options.get(CONF_MOTION_TIMEOUT, DEFAULT_MOTION_TIMEOUT))

    @property
    def off_mode(self) -> str:
        """Mode used when the light entity is turned off."""
        return str(self.config_entry.options.get(CONF_OFF_MODE, DEFAULT_OFF_MODE))

    # ---- Polling ---------------------------------------------------------

    async def _async_setup(self) -> None:
        try:
            await self._async_refresh_homes()
        except NetatmoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NetatmoApiError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_update_data(self) -> dict[str, PresenceCamera]:
        try:
            if time.monotonic() - self._homes_refreshed > HOMES_REFRESH_SECONDS:
                await self._async_refresh_homes()
            for home_id in self.home_ids:
                await self._async_update_home_status(home_id)
            await asyncio.gather(
                *(self._async_update_local(cam) for cam in self.cameras.values())
            )
            if not self.webhook_confirmed:
                await self._async_poll_events()
        except NetatmoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except NetatmoApiError as err:
            raise UpdateFailed(str(err)) from err
        return self.cameras

    async def _async_refresh_homes(self) -> None:
        body = await self.api.async_get_homes_data()
        for home in body.get("homes", []):
            home_id = home.get("id")
            for module in home.get("modules", []):
                if module.get("type") != MODULE_TYPE_PRESENCE or not module.get("id"):
                    continue
                cam_id = module["id"]
                name = module.get("name") or f"Presence {cam_id[-5:]}"
                if cam := self.cameras.get(cam_id):
                    cam.name = name
                    cam.home_id = home_id
                else:
                    self.cameras[cam_id] = PresenceCamera(cam_id, name, home_id)
                self.home_ids.add(home_id)
        self._homes_refreshed = time.monotonic()

    async def _async_update_home_status(self, home_id: str) -> None:
        body = await self.api.async_get_home_status(home_id)
        modules = {m.get("id"): m for m in body.get("home", {}).get("modules", [])}
        for cam in self.cameras.values():
            if cam.home_id != home_id:
                continue
            module = modules.get(cam.id)
            if module is None:
                cam.vpn_url = None
                continue
            cam.firmware = module.get("firmware_revision")
            cam.monitoring = module.get("monitoring")
            cam.cloud_floodlight = module.get("floodlight")
            cam.vpn_url = module.get("vpn_url")

    async def _async_update_local(self, cam: PresenceCamera) -> None:
        """Read the floodlight config, on the LAN if possible, else via Netatmo's relay."""
        if not cam.vpn_url:
            cam.reachable = False
            cam.base_url = None
            return
        # The relay URL changes every few hours; ask again for the LAN URL then.
        if cam.base_url is None or cam.probed_vpn_url != cam.vpn_url:
            await self._async_pick_base_url(cam)

        candidates = [cam.base_url]
        if cam.base_url != cam.vpn_url:
            candidates.append(cam.vpn_url)
        for url in candidates:
            try:
                cam.config = await self.api.async_get_floodlight_config(url)
            except NetatmoApiError as err:
                _LOGGER.debug("%s: cannot read floodlight config: %s", cam.name, err)
                continue
            cam.base_url = url
            cam.reachable = True
            return
        cam.reachable = False

    async def _async_pick_base_url(self, cam: PresenceCamera) -> None:
        cam.probed_vpn_url = cam.vpn_url
        cam.base_url = cam.vpn_url
        try:
            cam.local_url = await self.api.async_get_local_url(cam.vpn_url)
        except NetatmoApiError as err:
            _LOGGER.debug("%s: no LAN URL: %s", cam.name, err)
            cam.local_url = None
            return
        if await self.api.async_is_reachable(cam.local_url):
            cam.base_url = cam.local_url
        else:
            _LOGGER.info(
                "%s is not reachable on the LAN from Home Assistant; using Netatmo's relay",
                cam.name,
            )

    async def _async_poll_events(self) -> None:
        """Fallback when the webhook is not working: read recent events."""
        for home_id in self.home_ids:
            try:
                events = await self.api.async_get_events(home_id)
            except NetatmoAuthError:
                raise
            except NetatmoApiError as err:
                _LOGGER.debug("Cannot read events: %s", err)
                continue
            baseline = self._event_baseline.get(home_id)
            newest = baseline or 0
            found: list[tuple[int, str, str]] = []
            for event in events:
                cam_id = event.get("module_id")
                for kind, ts in detections_from_event(event):
                    newest = max(newest, ts)
                    # The first poll only sets the baseline, so old events don't fire.
                    if baseline is not None and ts > baseline and cam_id in self.cameras:
                        found.append((ts, cam_id, kind))
            self._event_baseline[home_id] = newest
            for _, cam_id, kind in sorted(found):
                self.async_handle_detection(cam_id, kind, "poll")

    # ---- Events ----------------------------------------------------------

    @callback
    def async_handle_detection(self, camera_id: str, kind: str, source: str) -> None:
        """Turn on the motion sensors for a detection and fire an HA event."""
        cam = self.cameras.get(camera_id)
        if cam is None:
            return
        now = time.monotonic()
        stamp = dt_util.utcnow()
        sensor_kinds = {MOTION_ANY} if kind == MOVEMENT else {MOTION_ANY, kind}
        for sensor_kind in sensor_kinds:
            self.motion[camera_id][sensor_kind] = now
            self.last_detection[camera_id][sensor_kind] = stamp
        self.hass.bus.async_fire(
            EVENT_DETECTION,
            {"camera_id": camera_id, "camera_name": cam.name, "type": kind, "source": source},
        )
        self.async_update_listeners()

    @callback
    def async_handle_webhook(self, data: dict[str, Any]) -> None:
        """Handle a push from Netatmo."""
        event_type = webhook_event_type(data)
        if event_type == "webhook_activation":
            _LOGGER.info("Netatmo webhook active: motion is now pushed in real time")
            self.webhook_confirmed = True
            return
        if event_type == "webhook_deactivation":
            _LOGGER.warning("Netatmo disabled the webhook; falling back to polling events")
            self.webhook_confirmed = False
            return

        camera_id = webhook_camera_id(data)
        if camera_id not in self.cameras:
            return
        if event_type == "light_mode":
            self.hass.async_create_task(self.async_request_refresh())
            return
        for kind in detections_from_webhook(data):
            self.async_handle_detection(camera_id, kind, "webhook")

    # ---- Commands --------------------------------------------------------

    async def async_set_floodlight(self, camera_id: str, changes: dict[str, Any]) -> None:
        """Change the floodlight config. Mode-only changes fall back to the cloud."""
        cam = self.cameras[camera_id]
        try:
            if not cam.base_url:
                raise NetatmoApiError("camera not reachable")
            await self.api.async_set_floodlight_config(cam.base_url, changes)
        except NetatmoApiError as err:
            if set(changes) != {"mode"}:
                raise HomeAssistantError(f"Could not update {cam.name}: {err}") from err
            _LOGGER.debug("%s: local call failed (%s), using the cloud", cam.name, err)
            try:
                await self.api.async_set_floodlight_cloud(cam.home_id, cam.id, changes["mode"])
            except NetatmoApiError as cloud_err:
                raise HomeAssistantError(f"Could not update {cam.name}: {cloud_err}") from cloud_err

        config = dict(cam.config or {})
        for key, value in changes.items():
            if key == "night" and isinstance(value, dict):
                config["night"] = {**config.get("night", {}), **value}
            else:
                config[key] = value
        cam.config = config
        self.async_update_listeners()
