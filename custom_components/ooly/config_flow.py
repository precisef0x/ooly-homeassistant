"""Config flow for the OOLY integration.

Two entry paths, both identifying the device by its MAC (stable unique_id) so a
manually-added device is recognised as the same one when discovered, and vice versa:
  - manual: user types an IP / hostname.
  - zeroconf: devices advertise mDNS `_http._tcp` with an instance name like
    `ooly-55f4` (filtered by `name: "ooly*"` in manifest.json).

After the device answers, the user picks the controller TYPE (tunable white / colour /
colour+white). This is an intent choice, not auto-detected from wiring, and can be
changed later via the reconfigure flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import OolyClient, OolyConnectionError
from .const import (
    CONF_DEVICE_TYPE,
    CONF_SCAN_INTERVAL,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEVICE_TYPES,
    DOMAIN,
    MAX_SCAN_INTERVAL_SECONDS,
    MIN_SCAN_INTERVAL_SECONDS,
)

if TYPE_CHECKING:
    # Type-only import: this path moved between HA versions, and the runtime code only
    # touches attributes of the passed object, so we never import it at runtime.
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo


def _name_from_hostname(hostname: str | None) -> str | None:
    """Turn an mDNS hostname (`ooly-55f4.local.`) into a display name (`ooly-55f4`)."""
    if not hostname:
        return None
    name = hostname.rstrip(".")
    if name.endswith(".local"):
        name = name[: -len(".local")]
    return name or None


def _type_schema(default: str) -> vol.Schema:
    """Schema for the manual device-type selection (labels come from translations)."""
    return vol.Schema(
        {
            vol.Required(CONF_DEVICE_TYPE, default=default): SelectSelector(
                SelectSelectorConfig(
                    options=DEVICE_TYPES,
                    translation_key="device_type",
                    mode=SelectSelectorMode.LIST,
                )
            )
        }
    )


def _reconfigure_schema(device_type: str, scan_interval: int) -> vol.Schema:
    """Schema for the reconfigure step: device type + polling interval."""
    return vol.Schema(
        {
            vol.Required(CONF_DEVICE_TYPE, default=device_type): SelectSelector(
                SelectSelectorConfig(
                    options=DEVICE_TYPES,
                    translation_key="device_type",
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_SCAN_INTERVAL, default=scan_interval): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL_SECONDS,
                    max=MAX_SCAN_INTERVAL_SECONDS,
                    step=1,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


class OolyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OOLY."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a controller by IP address / hostname."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            client = OolyClient(host, async_get_clientsession(self.hass))
            try:
                info = await client.async_identify()
            except OolyConnectionError:
                errors["base"] = "cannot_connect"
            else:
                self._host = host
                self._name = info["name"] or DEFAULT_NAME
                if info["mac"]:
                    await self.async_set_unique_id(info["mac"])
                    self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                else:
                    # No stable id available -> dedupe by host instead of an
                    # inconsistent `host:` unique_id.
                    self._async_abort_entries_match({CONF_HOST: host})
                return await self.async_step_pick_type()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_pick_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the controller type for a manually-added device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or DEFAULT_NAME,
                data={
                    CONF_HOST: self._host,
                    CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
                },
            )

        return self.async_show_form(
            step_id="pick_type",
            data_schema=_type_schema(DEFAULT_DEVICE_TYPE),
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered via mDNS (`ooly-*._http._tcp.local.`)."""
        host = str(discovery_info.ip_address)
        client = OolyClient(host, async_get_clientsession(self.hass))
        try:
            info = await client.async_identify()
        except OolyConnectionError:
            return self.async_abort(reason="cannot_connect")

        # Same unique_id scheme as the manual flow (device MAC) -> no duplicates.
        if info["mac"]:
            await self.async_set_unique_id(info["mac"])
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        else:
            self._async_abort_entries_match({CONF_HOST: host})

        self._host = host
        self._name = (
            _name_from_hostname(discovery_info.hostname) or info["name"] or DEFAULT_NAME
        )
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered controller and pick its type."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or DEFAULT_NAME,
                data={
                    CONF_HOST: self._host,
                    CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=_type_schema(DEFAULT_DEVICE_TYPE),
            description_placeholders={
                "name": self._name or DEFAULT_NAME,
                "host": self._host or "",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the controller type / polling interval of an existing entry."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                data={
                    **entry.data,
                    CONF_DEVICE_TYPE: user_input[CONF_DEVICE_TYPE],
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                },
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_schema(
                entry.data.get(CONF_DEVICE_TYPE, DEFAULT_DEVICE_TYPE),
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS),
            ),
        )
