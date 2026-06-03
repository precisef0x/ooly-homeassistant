"""Light platform for the OOLY integration.

One light per controller, modelled by the user-chosen device type:
  - ct       -> ColorMode.COLOR_TEMP                   (tunable white)
  - rgb      -> ColorMode.RGB                          (colour only)
  - rgb_cct  -> {ColorMode.RGB, ColorMode.COLOR_TEMP}  (colour OR tunable white)

Colour temperature is sent to the firmware NATIVELY as `cct_k` (the device turns it into
the wc/ww mix) — no channel maths, no HA colour_temp->rgbww conversion. Brightness rides
the device master `bri`. For rgb_cct the two domains are interlocked (a colour zeros the
white channels and a temperature zeros RGB), so the active color_mode is unambiguous and
the more-info card never "jumps".
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OolyApiError, device_base_url
from .const import (
    CONF_DEVICE_TYPE,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_NAME,
    DEVICE_TYPE_CT,
    DEVICE_TYPE_RGB,
    DEVICE_TYPE_RGB_CCT,
    DOMAIN,
)
from .coordinator import OolyCoordinator

# Firmware accepts tt_ms in 0..600000 (doc §6.2); clamp so a huge HA transition
# can't trigger an OUT_OF_RANGE rejection.
_MAX_TT_MS = 600_000

_SUPPORTED_MODES = {
    DEVICE_TYPE_CT: {ColorMode.COLOR_TEMP},
    DEVICE_TYPE_RGB: {ColorMode.RGB},
    # rgb_cct -> colour OR tunable white (interlocked):
    DEVICE_TYPE_RGB_CCT: {ColorMode.RGB, ColorMode.COLOR_TEMP},
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the OOLY light from a config entry."""
    coordinator: OolyCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OolyLight(coordinator, entry)])


class OolyLight(CoordinatorEntity[OolyCoordinator], LightEntity):
    """A single OOLY controller exposed as a light.

    State is read from the coordinator (real device state, for external-change sync),
    but commands also apply an OPTIMISTIC override so the UI/automations see the new
    state instantly. The override is cleared on the next coordinator refresh; we do NOT
    force an immediate refresh after a command (the device applies on its next render
    frame and `/state` returns last-applied, so a same-tick poll could overwrite the
    optimistic value with stale data).
    """

    _attr_has_entity_name = True
    _attr_name = None  # the device name is the light's name
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator: OolyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._device_type = entry.data.get(CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE)
        modes = _SUPPORTED_MODES.get(
            self._device_type, _SUPPORTED_MODES[DEFAULT_DEVICE_TYPE]
        )
        self._attr_supported_color_modes = modes
        self._has_color_temp = ColorMode.COLOR_TEMP in modes
        self._has_rgb = ColorMode.RGB in modes

        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = device_id
        if self._has_color_temp:
            self._attr_min_color_temp_kelvin = coordinator.cct_min_kelvin
            self._attr_max_color_temp_kelvin = coordinator.cct_max_kelvin

        self._optimistic: dict[str, Any] = {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title or DEFAULT_NAME,
            manufacturer="OOLY",
            model="LED Controller",
            configuration_url=device_base_url(entry.data[CONF_HOST]),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        # Real data arrived -> drop optimistic assumptions.
        self._optimistic = {}
        super()._handle_coordinator_update()

    # --- helpers -----------------------------------------------------------

    def _state(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("state") or {}

    def _aliases(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("aliases") or {}

    @staticmethod
    def _chan(state: dict[str, Any], key: str) -> int:
        # Device channels are ints; coerce a stray null to 0 defensively.
        value = state.get(key)
        return int(value) if value is not None else 0

    # --- state properties --------------------------------------------------

    @property
    def color_mode(self) -> ColorMode:
        if "mode" in self._optimistic:
            return self._optimistic["mode"]
        if not self._has_rgb:
            return ColorMode.COLOR_TEMP
        if not self._has_color_temp:
            return ColorMode.RGB
        # rgb_cct: white lit (cct_k available) => COLOR_TEMP, else RGB. The interlock
        # (temp zeros RGB, colour zeros white) keeps this unambiguous.
        return (
            ColorMode.COLOR_TEMP
            if self._aliases().get("cct_k") is not None
            else ColorMode.RGB
        )

    @property
    def is_on(self) -> bool:
        if "on" in self._optimistic:
            return self._optimistic["on"]
        return bool(self._state().get("on"))

    @property
    def brightness(self) -> int | None:
        if "bri" in self._optimistic:
            return self._optimistic["bri"]
        value = self._state().get("bri")
        return int(value) if value is not None else None

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        if "rgb" in self._optimistic:
            return self._optimistic["rgb"]
        state = self._state()
        return (self._chan(state, "r"), self._chan(state, "g"), self._chan(state, "b"))

    @property
    def color_temp_kelvin(self) -> int | None:
        if "cct_k" in self._optimistic:
            return self._optimistic["cct_k"]
        value = self._aliases().get("cct_k")
        return int(value) if value is not None else None

    # --- commands ----------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        body: dict[str, Any] = {"on": True}
        optimistic: dict[str, Any] = {"on": True}

        if ATTR_BRIGHTNESS in kwargs:
            brightness = int(kwargs[ATTR_BRIGHTNESS])
            body["bri"] = brightness
            optimistic["bri"] = brightness

        if self._has_color_temp and ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            # Native tunable white: the firmware turns cct_k into the wc/ww mix. Pin the
            # white-domain brightness (cct_bri=0 would stay dark) and zero RGB so it's
            # pure white at the requested temperature.
            body.update({"cct_k": kelvin, "cct_bri": 255, "r": 0, "g": 0, "b": 0})
            optimistic.update({"cct_k": kelvin, "mode": ColorMode.COLOR_TEMP})
        elif self._has_rgb and ATTR_RGB_COLOR in kwargs:
            r, g, b = (int(c) for c in kwargs[ATTR_RGB_COLOR])
            # Pure colour: zero the white channels.
            body.update({"r": r, "g": g, "b": b, "wc": 0, "ww": 0})
            optimistic.update({"rgb": (r, g, b), "mode": ColorMode.RGB})
        elif self._device_type == DEVICE_TYPE_CT:
            # Bare on/brightness for a CT light: keep white lit, colour off.
            body.update({"r": 0, "g": 0, "b": 0, "cct_bri": 255})
        elif self._device_type == DEVICE_TYPE_RGB:
            body.update({"wc": 0, "ww": 0})
        # rgb_cct with no colour attribute: leave the current domain untouched.

        if ATTR_TRANSITION in kwargs:
            body["tt_ms"] = min(int(float(kwargs[ATTR_TRANSITION]) * 1000), _MAX_TT_MS)

        await self._send(body)
        self._optimistic.update(optimistic)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        body: dict[str, Any] = {"on": False}
        if ATTR_TRANSITION in kwargs:
            body["tt_ms"] = min(int(float(kwargs[ATTR_TRANSITION]) * 1000), _MAX_TT_MS)
        await self._send(body)
        self._optimistic = {"on": False}
        self.async_write_ha_state()

    async def _send(self, body: dict[str, Any]) -> None:
        try:
            await self.coordinator.client.async_post_state(body)
        except OolyApiError as err:
            raise HomeAssistantError(f"OOLY command failed: {err}") from err
