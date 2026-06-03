"""Minimal async HTTP client for an OOLY controller.

The firmware exposes a plain HTTP/JSON API on port 80 (no auth). Only the few
endpoints needed for control/state/identification are used here:
  - GET  /state                -> current state (on, bri, r/g/b/wc/ww, aliases.cct_k, ...)
  - POST /state                -> apply a JSON patch ({"on":true,"bri":128,...})
  - GET  /health               -> "OK" (reachability check)
  - GET  /snapshot?view=esnow  -> wifi_mac_sta (stable per-device id)
  - GET  /config/get           -> device_name + CCT range (cct_ww_kelvin/cct_wc_kelvin)
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import (
    HTTP_TIMEOUT_SECONDS,
    POST_MAX_ATTEMPTS,
    POST_RETRY_AFTER_CAP_SECONDS,
    POST_RETRY_BUDGET_SECONDS,
)


class OolyApiError(Exception):
    """A request to the device failed or returned an unexpected payload."""


class OolyConnectionError(OolyApiError):
    """The device could not be reached (network/timeout)."""


def device_base_url(host: str) -> str:
    """Return the controller base URL (``http://host``), bracketing IPv6 literals."""
    if host.count(":") >= 2 and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}"


def _retry_after_seconds(headers: Any, body: Any) -> float:
    """Best-effort retry delay from a 503/403 response (body hint, then header, else 1s)."""
    if isinstance(body, dict):
        ms = body.get("retry_after_ms")
        if isinstance(ms, (int, float)) and ms > 0:
            return min(float(ms) / 1000.0, POST_RETRY_AFTER_CAP_SECONDS)
    raw = headers.get("Retry-After") if headers is not None else None
    if raw:
        try:
            return min(float(raw), POST_RETRY_AFTER_CAP_SECONDS)
        except (TypeError, ValueError):
            pass
    return 1.0


class OolyClient:
    """Thin wrapper around the controller's HTTP API."""

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        self._host = host.strip().rstrip("/")
        self._session = session

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> str:
        return f"{device_base_url(self._host)}{path}"

    @property
    def _timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    async def _get_json(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(self._url(path), timeout=self._timeout) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OolyConnectionError(str(err)) from err
        if not isinstance(data, dict):
            raise OolyApiError(f"unexpected JSON from {path}: {data!r}")
        return data

    async def async_get_state(self) -> dict[str, Any]:
        """Return the parsed GET /state document ({'state': {...}, 'aliases': {...}})."""
        data = await self._get_json("/state")
        if "state" not in data:
            raise OolyApiError(f"missing 'state' in /state response: {data!r}")
        return data

    async def async_post_state(self, payload: dict[str, Any]) -> None:
        """POST a state patch.

        Retries transient device states the firmware documents as retryable:
          - 503 BUSY/STORE_BUSY (single-slot mailbox), honouring Retry-After/retry_after_ms;
          - 403 BOOT_NOT_CONFIRMED (write gate for ~5s after boot).
        Hard errors (400 validation, 403 POLICY_REJECT, ...) raise immediately.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + POST_RETRY_BUDGET_SECONDS
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._session.post(
                    self._url("/state"), json=payload, timeout=self._timeout
                ) as resp:
                    status = resp.status
                    try:
                        data: Any = await resp.json(content_type=None)
                    except (aiohttp.ClientError, ValueError):
                        data = None
                    retry_after = _retry_after_seconds(resp.headers, data)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise OolyConnectionError(str(err)) from err

            if status == 200 and isinstance(data, dict) and data.get("ok"):
                return

            error = data.get("error") if isinstance(data, dict) else None
            transient = status == 503 or (status == 403 and error == "BOOT_NOT_CONFIRMED")
            if (
                transient
                and attempt < POST_MAX_ATTEMPTS
                and loop.time() + retry_after <= deadline
            ):
                await asyncio.sleep(retry_after)
                continue

            raise OolyApiError(
                f"POST /state rejected (status={status}, body={data!r})"
            )

    async def async_get_cct_bounds(self) -> tuple[int, int] | None:
        """Return (min_kelvin, max_kelvin) from /config/get, or None if unavailable.

        cct_ww_kelvin is the warm (lower) bound, cct_wc_kelvin the cold (upper) bound.
        """
        try:
            cfg = await self._get_json("/config/get")
        except OolyApiError:
            return None
        try:
            lo = int(cfg["cct_ww_kelvin"])
            hi = int(cfg["cct_wc_kelvin"])
        except (KeyError, TypeError, ValueError):
            return None
        if lo <= 0 or hi <= 0 or lo >= hi:
            return None
        return (lo, hi)

    async def async_identify(self) -> dict[str, Any]:
        """Probe the device for config-flow.

        Returns {'mac': <str|None>, 'name': <str|None>}. Raises OolyConnectionError
        if the device is not reachable at all (health check fails).
        """
        # Reachability gate.
        try:
            async with self._session.get(self._url("/health"), timeout=self._timeout) as resp:
                resp.raise_for_status()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OolyConnectionError(str(err)) from err

        mac: str | None = None
        name: str | None = None

        # Stable per-device id (best-effort; may be absent if ESPNOW disabled).
        try:
            snap = await self._get_json("/snapshot?view=esnow")
            raw = str(snap.get("wifi_mac_sta", "")).strip().lower()
            if raw and raw != "00:00:00:00:00:00":
                mac = raw
        except OolyApiError:
            pass

        # Friendly name (best-effort).
        try:
            cfg = await self._get_json("/config/get")
            candidate = str(cfg.get("device_name", "")).strip()
            if candidate:
                name = candidate
        except OolyApiError:
            pass

        return {"mac": mac, "name": name}
