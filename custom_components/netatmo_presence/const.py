"""Constants for the Netatmo Presence integration."""

from __future__ import annotations

DOMAIN = "netatmo_presence"

OAUTH2_AUTHORIZE = "https://api.netatmo.com/oauth2/authorize"
OAUTH2_TOKEN = "https://api.netatmo.com/oauth2/token"
SCOPES = ["read_presence", "write_presence", "access_presence"]

MODULE_TYPE_PRESENCE = "NOC"

# Config entry data
CONF_WEBHOOK_ID = "webhook_id"
CONF_CLOUDHOOK_URL = "cloudhook_url"

# Options
CONF_OFF_MODE = "off_mode"
CONF_MOTION_TIMEOUT = "motion_timeout"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_USE_WEBHOOK = "use_webhook"

MODE_ON = "on"
MODE_OFF = "off"
MODE_AUTO = "auto"
MODES = [MODE_ON, MODE_OFF, MODE_AUTO]

DEFAULT_OFF_MODE = MODE_AUTO
DEFAULT_MOTION_TIMEOUT = 30
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_USE_WEBHOOK = True

# Motion sensors: "motion" fires on any detection.
MOTION_ANY = "motion"
SENSOR_KINDS = [MOTION_ANY, "human", "animal", "vehicle"]

# Keys of the "night" block in the floodlight config.
NIGHT_TRIGGERS = ["person", "vehicle", "animal", "movement", "always"]

EVENT_DETECTION = f"{DOMAIN}_event"

HOMES_REFRESH_SECONDS = 3600
