"""Client for the Netatmo cloud API and the Presence local API.

This module only depends on aiohttp so it can be tested outside Home Assistant.
Error messages never include URLs: the camera URLs contain access keys.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.netatmo.com/api"
CLOUD_TIMEOUT = aiohttp.ClientTimeout(total=20)
LOCAL_TIMEOUT = aiohttp.ClientTimeout(total=8)
PROBE_TIMEOUT = aiohttp.ClientTimeout(total=3)

# Netatmo error codes meaning the token is invalid, expired or lacks scopes.
AUTH_ERROR_CODES = {2, 3, 13}

DETECTION_TYPES = ("human", "animal", "vehicle")
MOVEMENT = "movement"
MOTION_EVENT_TYPES = {"outdoor", MOVEMENT, *DETECTION_TYPES}


class NetatmoApiError(Exception):
    """Error talking to Netatmo or to the camera."""


class NetatmoAuthError(NetatmoApiError):
    """The token was rejected; the user has to sign in again."""


class OAuthSession(Protocol):
    """The part of Home Assistant's OAuth2Session that we use."""

    async def async_ensure_token_valid(self) -> None:
        """Refresh the token if needed."""

    async def async_request(
        self, method: str, url: str, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """Make an authenticated request."""


def _is_auth_failure(err: Exception) -> bool:
    status = getattr(err, "status", None)
    if isinstance(status, int) and 400 <= status < 500:
        return True
    name = type(err).__name__
    return "Reauth" in name or "AuthFailed" in name


class NetatmoPresenceApi:
    """Netatmo API calls used by the integration."""

    def __init__(self, oauth: OAuthSession, websession: aiohttp.ClientSession) -> None:
        self._oauth = oauth
        self._websession = websession

    # ---- Cloud API -------------------------------------------------------

    async def _cloud(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        try:
            await self._oauth.async_ensure_token_valid()
        except Exception as err:  # noqa: BLE001 - HA raises several types here
            if _is_auth_failure(err):
                raise NetatmoAuthError("token refresh rejected") from err
            raise NetatmoApiError(f"token refresh failed ({type(err).__name__})") from err

        try:
            resp = await self._oauth.async_request(
                method, f"{API_BASE}/{endpoint}", timeout=CLOUD_TIMEOUT, **kwargs
            )
            async with resp:
                status = resp.status
                payload = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise NetatmoApiError(f"{endpoint}: {type(err).__name__}") from err

        if status < 400 and isinstance(payload, dict) and "error" not in payload:
            return payload

        error = payload.get("error") if isinstance(payload, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
        message = error.get("message") if isinstance(error, dict) else error
        if status == 401 or code in AUTH_ERROR_CODES:
            raise NetatmoAuthError(f"{endpoint}: {message}")
        raise NetatmoApiError(f"{endpoint}: HTTP {status} {message}")

    async def async_get_homes_data(self) -> dict[str, Any]:
        """Return homes, modules and user info."""
        return (await self._cloud("GET", "homesdata")).get("body", {})

    async def async_get_home_status(self, home_id: str) -> dict[str, Any]:
        """Return the live status of a home's modules."""
        payload = await self._cloud("GET", "homestatus", params={"home_id": home_id})
        return payload.get("body", {})

    async def async_get_events(self, home_id: str, size: int = 20) -> list[dict[str, Any]]:
        """Return the latest events of a home, newest first."""
        payload = await self._cloud(
            "GET", "getevents", params={"home_id": home_id, "size": size}
        )
        return payload.get("body", {}).get("home", {}).get("events", []) or []

    async def async_set_floodlight_cloud(self, home_id: str, camera_id: str, mode: str) -> None:
        """Set the floodlight mode (on/off/auto) through the cloud. No brightness."""
        await self._cloud(
            "POST",
            "setstate",
            json={"home": {"id": home_id, "modules": [{"id": camera_id, "floodlight": mode}]}},
        )

    async def async_add_webhook(self, url: str) -> None:
        """Ask Netatmo to push events to this URL."""
        await self._cloud("POST", "addwebhook", data={"url": url})

    async def async_drop_webhook(self) -> None:
        """Stop Netatmo pushing events for this app."""
        await self._cloud("POST", "dropwebhook")

    # ---- Camera local API ------------------------------------------------

    async def _local(
        self,
        base_url: str,
        command: str,
        params: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout = LOCAL_TIMEOUT,
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/command/{command}"
        try:
            async with self._websession.get(url, params=params, timeout=timeout) as resp:
                status = resp.status
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NetatmoApiError(f"{command}: {type(err).__name__}") from err
        if status >= 400:
            raise NetatmoApiError(f"{command}: HTTP {status}")
        try:
            data = json.loads(text)
        except ValueError as err:
            raise NetatmoApiError(f"{command}: invalid response") from err
        if not isinstance(data, dict):
            raise NetatmoApiError(f"{command}: invalid response")
        return data

    async def async_get_local_url(self, vpn_url: str) -> str:
        """Ask the camera (through Netatmo's relay) for its LAN URL."""
        local_url = (await self._local(vpn_url, "ping")).get("local_url")
        if not local_url:
            raise NetatmoApiError("ping: no local_url")
        return str(local_url)

    async def async_is_reachable(self, base_url: str) -> bool:
        """Return True if the camera answers at this URL."""
        try:
            await self._local(base_url, "ping", timeout=PROBE_TIMEOUT)
        except NetatmoApiError:
            return False
        return True

    async def async_get_floodlight_config(self, base_url: str) -> dict[str, Any]:
        """Return e.g. {"intensity": 100, "mode": "auto", "night": {...}}."""
        return await self._local(base_url, "floodlight_get_config")

    async def async_set_floodlight_config(self, base_url: str, changes: dict[str, Any]) -> None:
        """Change part of the floodlight config. The camera merges partial updates."""
        data = await self._local(
            base_url,
            "floodlight_set_config",
            params={"config": json.dumps(changes, separators=(",", ":"))},
        )
        if data.get("status") != "ok":
            raise NetatmoApiError(f"floodlight_set_config: {data.get('status')}")


# ---- Event parsing -------------------------------------------------------


def detections_from_event(event: dict[str, Any]) -> list[tuple[str, int]]:
    """Return (kind, unix time) pairs from a getevents item."""
    subevents = event.get("subevents") or []
    if subevents:
        return [
            (
                sub.get("type") if sub.get("type") in DETECTION_TYPES else MOVEMENT,
                int(sub.get("time") or event.get("time") or 0),
            )
            for sub in subevents
            if isinstance(sub, dict)
        ]
    event_type = event.get("type")
    if event_type in MOTION_EVENT_TYPES:
        kind = event_type if event_type in DETECTION_TYPES else MOVEMENT
        return [(kind, int(event.get("time") or 0))]
    return []


def webhook_event_type(data: dict[str, Any]) -> str:
    """Return the event type of a webhook push, e.g. "human" or "light_mode"."""
    event_type = data.get("event_type")
    if event_type:
        return str(event_type)
    push_type = str(data.get("push_type") or "")
    # push_type looks like "NOC-human"
    return push_type.split("-", 1)[1] if "-" in push_type else push_type


def webhook_camera_id(data: dict[str, Any]) -> str | None:
    """Return the camera id (its MAC) of a webhook push."""
    for key in ("camera_id", "device_id", "module_id"):
        if data.get(key):
            return str(data[key])
    return None


def detections_from_webhook(data: dict[str, Any]) -> list[str]:
    """Return the detection kinds in a webhook push."""
    event_type = webhook_event_type(data)
    if event_type == "outdoor":
        kinds = [
            item.get("type")
            for item in data.get("event_list") or []
            if isinstance(item, dict)
        ]
        return [k if k in DETECTION_TYPES else MOVEMENT for k in kinds] or [MOVEMENT]
    if event_type in DETECTION_TYPES:
        return [event_type]
    if event_type == MOVEMENT:
        return [MOVEMENT]
    return []
