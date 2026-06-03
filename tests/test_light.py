"""Tests for the OOLY light entity (per-type modes, command bodies, interlock)."""

from __future__ import annotations

from homeassistant.components.light import ColorMode
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ooly.const import (
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_CT,
    DEVICE_TYPE_RGB,
    DEVICE_TYPE_RGB_CCT,
    DOMAIN,
)

HOST = "1.2.3.4"
MAC = "aa:bb:cc:dd:ee:ff"


async def _setup(hass, aioclient_mock, device_type, state=None, aliases=None):
    state = state or {"on": True, "bri": 128, "r": 0, "g": 0, "b": 0, "wc": 0, "ww": 0}
    aliases = aliases if aliases is not None else {"cct_k": None}
    aioclient_mock.get(
        f"http://{HOST}/state", json={"ok": True, "state": state, "aliases": aliases}
    )
    aioclient_mock.get(
        f"http://{HOST}/config/get", json={"cct_ww_kelvin": 2700, "cct_wc_kelvin": 6500}
    )
    aioclient_mock.post(f"http://{HOST}/state", json={"ok": True})
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        title="Test",
        data={CONF_HOST: HOST, CONF_DEVICE_TYPE: device_type},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id("light", DOMAIN, MAC)
    assert entity_id
    return entity_id


def _last_post_body(aioclient_mock):
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts, "no POST /state was made"
    return posts[-1][2]


async def _turn_on(hass, entity_id, **kwargs):
    await hass.services.async_call(
        "light", "turn_on", {ATTR_ENTITY_ID: entity_id, **kwargs}, blocking=True
    )


async def test_ct_supported_modes(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_CT)
    attrs = hass.states.get(entity_id).attributes
    assert attrs["supported_color_modes"] == [ColorMode.COLOR_TEMP]
    assert attrs["min_color_temp_kelvin"] == 2700
    assert attrs["max_color_temp_kelvin"] == 6500


async def test_rgb_supported_modes(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB)
    assert hass.states.get(entity_id).attributes["supported_color_modes"] == [ColorMode.RGB]


async def test_rgb_cct_supported_modes(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB_CCT)
    attrs = hass.states.get(entity_id).attributes
    assert set(attrs["supported_color_modes"]) == {ColorMode.RGB, ColorMode.COLOR_TEMP}


async def test_ct_turn_on_sends_native_cct(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_CT)
    await _turn_on(hass, entity_id, color_temp_kelvin=3000, brightness=100)
    body = _last_post_body(aioclient_mock)
    assert body["on"] is True
    assert body["cct_k"] == 3000
    assert body["cct_bri"] == 255
    assert body["bri"] == 100
    assert body["r"] == 0 and body["g"] == 0 and body["b"] == 0
    assert "wc" not in body  # the cct path never writes raw white channels


async def test_rgb_turn_on_zeros_white(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB)
    await _turn_on(hass, entity_id, rgb_color=(255, 10, 0), brightness=200)
    body = _last_post_body(aioclient_mock)
    assert body["r"] == 255 and body["g"] == 10 and body["b"] == 0
    assert body["wc"] == 0 and body["ww"] == 0
    assert body["bri"] == 200


async def test_rgb_cct_color_temp_zeros_rgb(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB_CCT)
    await _turn_on(hass, entity_id, color_temp_kelvin=4000)
    body = _last_post_body(aioclient_mock)
    assert body["cct_k"] == 4000
    assert body["r"] == 0 and body["g"] == 0 and body["b"] == 0


async def test_rgb_cct_color_mode_color_temp_when_white_lit(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB_CCT, aliases={"cct_k": 3500})
    assert hass.states.get(entity_id).attributes["color_mode"] == ColorMode.COLOR_TEMP


async def test_rgb_cct_color_mode_rgb_when_no_white(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB_CCT, aliases={"cct_k": None})
    assert hass.states.get(entity_id).attributes["color_mode"] == ColorMode.RGB


async def test_transition_maps_to_tt_ms(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB)
    await _turn_on(hass, entity_id, rgb_color=(1, 2, 3), transition=3)
    assert _last_post_body(aioclient_mock)["tt_ms"] == 3000


async def test_turn_off(hass, aioclient_mock):
    entity_id = await _setup(hass, aioclient_mock, DEVICE_TYPE_RGB)
    await hass.services.async_call(
        "light", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert _last_post_body(aioclient_mock) == {"on": False}
