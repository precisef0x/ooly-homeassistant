"""Tests for the OOLY HTTP client (retries, IPv6 URLs, CCT bounds).

These exercise OolyClient against a hand-rolled fake aiohttp session, so they need no
running Home Assistant — only that the package imports.
"""

from __future__ import annotations

import aiohttp
import pytest

from custom_components.ooly.api import OolyApiError, OolyClient, device_base_url


class _Resp:
    def __init__(self, status, body, headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def json(self, content_type=None):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        return self._responses.pop(0)

    def get(self, url, timeout=None):
        self.gets.append(url)
        return self._responses.pop(0)


def test_url_brackets_ipv6_only():
    assert OolyClient("fe80::1", _Session([]))._url("/state") == "http://[fe80::1]/state"
    assert OolyClient("192.168.1.5", _Session([]))._url("/s") == "http://192.168.1.5/s"
    assert OolyClient("ooly-55f4.local", _Session([]))._url("/h") == "http://ooly-55f4.local/h"


def test_device_base_url():
    assert device_base_url("192.168.1.5") == "http://192.168.1.5"
    assert device_base_url("fe80::1") == "http://[fe80::1]"
    assert device_base_url("[::1]") == "http://[::1]"


async def test_post_state_ok():
    sess = _Session([_Resp(200, {"ok": True})])
    await OolyClient("h", sess).async_post_state({"on": True})
    assert len(sess.posts) == 1


async def test_post_state_retries_busy_then_ok():
    sess = _Session(
        [
            _Resp(503, {"ok": False, "error": "BUSY", "retry_after_ms": 1}),
            _Resp(200, {"ok": True}),
        ]
    )
    await OolyClient("h", sess).async_post_state({"on": True})
    assert len(sess.posts) == 2


async def test_post_state_retries_boot_not_confirmed_then_ok():
    sess = _Session(
        [
            _Resp(403, {"ok": False, "error": "BOOT_NOT_CONFIRMED"}),
            _Resp(200, {"ok": True}),
        ]
    )
    await OolyClient("h", sess).async_post_state({"on": True})
    assert len(sess.posts) == 2


async def test_post_state_400_hard_fails_without_retry():
    sess = _Session([_Resp(400, {"ok": False, "error": "OUT_OF_RANGE", "field": "wc"})])
    with pytest.raises(OolyApiError):
        await OolyClient("h", sess).async_post_state({"wc": 999})
    assert len(sess.posts) == 1


async def test_post_state_policy_reject_hard_fails_without_retry():
    sess = _Session(
        [_Resp(403, {"ok": False, "error": "POLICY_REJECT", "reason": "REJECT_INVALID"})]
    )
    with pytest.raises(OolyApiError):
        await OolyClient("h", sess).async_post_state({"on": True})
    assert len(sess.posts) == 1


async def test_get_cct_bounds_ok():
    sess = _Session([_Resp(200, {"cct_ww_kelvin": 2700, "cct_wc_kelvin": 6500})])
    assert await OolyClient("h", sess).async_get_cct_bounds() == (2700, 6500)


async def test_get_cct_bounds_missing_returns_none():
    sess = _Session([_Resp(200, {"foo": 1})])
    assert await OolyClient("h", sess).async_get_cct_bounds() is None
