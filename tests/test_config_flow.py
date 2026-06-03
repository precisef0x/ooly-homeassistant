"""Tests for the OOLY config flow (user, zeroconf dedup, reconfigure)."""

from __future__ import annotations

import aiohttp
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ooly.const import (
    CONF_DEVICE_TYPE,
    CONF_SCAN_INTERVAL,
    DEVICE_TYPE_CT,
    DEVICE_TYPE_RGB_CCT,
    DOMAIN,
)

HOST = "1.2.3.4"
MAC = "aa:bb:cc:dd:ee:ff"


def _mock_device(aioclient_mock, name="Kitchen", mac=MAC):
    """Mock every endpoint identify + entry setup need."""
    aioclient_mock.get(f"http://{HOST}/health", text="OK")
    aioclient_mock.get(f"http://{HOST}/snapshot?view=esnow", json={"wifi_mac_sta": mac})
    aioclient_mock.get(
        f"http://{HOST}/config/get",
        json={"device_name": name, "cct_ww_kelvin": 2700, "cct_wc_kelvin": 6500},
    )
    aioclient_mock.get(
        f"http://{HOST}/state",
        json={"ok": True, "state": {"on": False, "bri": 0}, "aliases": {"cct_k": None}},
    )


async def test_user_flow_creates_entry(hass, aioclient_mock):
    _mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["step_id"] == "pick_type"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: DEVICE_TYPE_CT}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_DEVICE_TYPE: DEVICE_TYPE_CT}
    assert result["result"].unique_id == MAC
    assert result["title"] == "Kitchen"


async def test_user_flow_cannot_connect(hass, aioclient_mock):
    aioclient_mock.get(f"http://{HOST}/health", exc=aiohttp.ClientError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_aborts(hass, aioclient_mock):
    MockConfigEntry(domain=DOMAIN, unique_id=MAC, data={CONF_HOST: HOST}).add_to_hass(hass)
    _mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: HOST})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_type_and_interval(hass, aioclient_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        title="Kitchen",
        data={CONF_HOST: HOST, CONF_DEVICE_TYPE: DEVICE_TYPE_RGB_CCT},
    )
    entry.add_to_hass(hass)
    _mock_device(aioclient_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
    )
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_TYPE: DEVICE_TYPE_CT, CONF_SCAN_INTERVAL: 5}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_DEVICE_TYPE] == DEVICE_TYPE_CT
    assert entry.data[CONF_SCAN_INTERVAL] == 5
