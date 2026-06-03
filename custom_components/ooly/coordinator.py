"""DataUpdateCoordinator that polls an OOLY controller's /state."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OolyApiError, OolyClient
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    MAX_COLOR_TEMP_KELVIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_COLOR_TEMP_KELVIN,
    MIN_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class OolyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls GET /state and exposes the parsed document to entities."""

    def __init__(self, hass: HomeAssistant, client: OolyClient, entry: ConfigEntry) -> None:
        interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        interval = max(MIN_SCAN_INTERVAL_SECONDS, min(MAX_SCAN_INTERVAL_SECONDS, int(interval)))
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.entry = entry
        # Per-device colour-temperature range; real values loaded from /config/get,
        # these const fallbacks are used only if that read fails.
        self.cct_min_kelvin = MIN_COLOR_TEMP_KELVIN
        self.cct_max_kelvin = MAX_COLOR_TEMP_KELVIN

    async def async_load_cct_bounds(self) -> None:
        """Read the device's real CCT range once (best-effort; keeps fallback on failure)."""
        bounds = await self.client.async_get_cct_bounds()
        if bounds is not None:
            self.cct_min_kelvin, self.cct_max_kelvin = bounds

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_state()
        except OolyApiError as err:
            raise UpdateFailed(str(err)) from err
