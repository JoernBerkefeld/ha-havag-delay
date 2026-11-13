"""Constants for HAVAG Delay."""

DOMAIN = "havag_delay"

CONF_STOP_QUERY = "stop_query"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LINE = "line"
CONF_DIRECTION = "direction"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_OFFSET_MINUTES = "offset_minutes"

SERVICE_GET_DEPARTURE = "get_departure"
# How far past the earliest wanted departure to look for one.
UPCOMING_WINDOW_MINUTES = 60
