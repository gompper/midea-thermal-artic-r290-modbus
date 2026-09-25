"""Constants for the Midea M-Thermal integration."""

from datetime import timedelta

DOMAIN = "midea_m_thermal"
MANUFACTURER = "Midea"

CONF_UNIT_ID = "unit_id"

DEFAULT_NAME = "Heat pump"
# The Elfin EW11 serves Modbus TCP on 8899; the heat pump ships as unit 1.
DEFAULT_PORT = 8899
DEFAULT_UNIT_ID = 1

SCAN_INTERVAL = timedelta(seconds=30)
