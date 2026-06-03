"""Constants for the OOLY integration."""

DOMAIN = "ooly"

DEFAULT_NAME = "OOLY"

# --- Device colour capability -------------------------------------------------
# Chosen by the user when adding the device (and changeable via reconfigure).
# It is a usage/intent choice, NOT auto-detected from the controller's wiring:
# a controller may have all 5 PWM roles populated yet be used as tunable-white only.
CONF_DEVICE_TYPE = "device_type"

DEVICE_TYPE_CT = "ct"  # tunable white only -> ColorMode.COLOR_TEMP
DEVICE_TYPE_RGB = "rgb"  # colour only -> ColorMode.RGB
DEVICE_TYPE_RGB_CCT = "rgb_cct"  # colour OR tunable white -> {ColorMode.RGB, ColorMode.COLOR_TEMP}
DEVICE_TYPES = [DEVICE_TYPE_CT, DEVICE_TYPE_RGB, DEVICE_TYPE_RGB_CCT]
DEFAULT_DEVICE_TYPE = DEVICE_TYPE_RGB_CCT

# Background poll cadence (seconds). The light is optimistic for its own commands, so this
# only governs how fast EXTERNAL changes (remote/other client) and offline detection are
# picked up. Per-device, tunable in the Reconfigure flow.
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL_SECONDS = 10
MIN_SCAN_INTERVAL_SECONDS = 2
MAX_SCAN_INTERVAL_SECONDS = 600

# Per-request HTTP timeout (seconds).
HTTP_TIMEOUT_SECONDS = 5

# POST /state retry policy for transient device states (503 BUSY, 403 BOOT_NOT_CONFIRMED).
POST_MAX_ATTEMPTS = 4
POST_RETRY_BUDGET_SECONDS = 6.0
POST_RETRY_AFTER_CAP_SECONDS = 2.0

# Colour-temperature slider bounds (Kelvin), used as a FALLBACK only. The real
# per-device range is read at setup from /config/get (cct_ww_kelvin..cct_wc_kelvin).
MIN_COLOR_TEMP_KELVIN = 2700
MAX_COLOR_TEMP_KELVIN = 6500
