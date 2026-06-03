# OOLY for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration for OOLY Wi‑Fi LED
controllers. It communicates with each controller directly over its local HTTP/JSON API;
no cloud service or authentication is involved. The controllers are ESP‑based and expose
five PWM channels (R, G, B, cold white, warm white).

[![CI](https://github.com/precisef0x/ooly-homeassistant/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/precisef0x/ooly-homeassistant/actions/workflows/ci.yml)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

## Overview

- Local control over HTTP (`iot_class: local_polling`); no cloud dependency.
- UI configuration (config flow) with mDNS/zeroconf discovery; multiple controllers are
  supported.
- Per‑device controller type — tunable white, colour, or colour + white — selected at
  setup and changeable later via the reconfigure flow.
- Light control: power, brightness, RGB colour, colour temperature, and transitions.
- Optimistic state with periodic background polling for external changes and availability.
- Automatic retry of transient device responses (`503 BUSY`, post‑boot
  `403 BOOT_NOT_CONFIRMED`).
- Stable device identity by MAC address.

## Supported device types

The controller type reflects intended use rather than wiring: a five‑channel controller
may be operated as tunable white only.

| Type | Colour mode | Controls |
| --- | --- | --- |
| Tunable white (CCT) | `color_temp` | Brightness, colour temperature |
| Colour (RGB) | `rgb` | Brightness, colour |
| Colour + white (RGB + CCT) | `rgb` + `color_temp` | Brightness; colour or colour temperature |

For the RGB + CCT type the two domains are interlocked: setting a colour clears the white
channels, and selecting a colour temperature clears the colour channels, so the active
colour mode is always unambiguous. The type can be changed under **Settings → Devices &
Services → (device) → ⋮ → Reconfigure**.

## Requirements

- Home Assistant 2024.8 or newer.
- An OOLY controller reachable on the local network (HTTP API on port 80).
- A static or DHCP‑reserved address for the controller is recommended.

## Installation

### HACS (custom repository)

1. In HACS, open **Integrations → ⋮ → Custom repositories**.
2. Add the repository URL with category **Integration**, then install it.
3. Restart Home Assistant.

### Manual

1. Copy the `custom_components/ooly` directory into the Home Assistant configuration
   directory, resulting in `<config>/custom_components/ooly/`.
2. Restart Home Assistant.

## Configuration

1. Open **Settings → Devices & Services → Add Integration** and select **OOLY**.
2. Enter the controller's IP address or hostname.
3. Select the controller type (CT / RGB / RGB + CCT).

Discovered controllers also appear under **Settings → Devices & Services → Discovered**.

## Entities

Each controller is represented by a single `light` entity. For the RGB + CCT type it
provides both a colour control and a colour‑temperature control; for the CT and RGB types
it provides the corresponding control only.

## Behaviour

- **State.** Commands are applied optimistically for immediate feedback. The controller is
  polled in the background (10 seconds by default, configurable via the reconfigure flow)
  to reflect external changes and offline state.
- **Colour temperature.** Sent to the controller as `cct_k`. The supported range is read
  from the device (`cct_ww_kelvin`..`cct_wc_kelvin`); the constants in `const.py` are a
  fallback.
- **Resilience.** Transient `503 BUSY` and post‑boot `403 BOOT_NOT_CONFIRMED` responses
  are retried automatically, honouring `Retry-After`.

## Troubleshooting

- **Address changes.** A reserved address avoids this. Otherwise the stored address is
  updated on the next discovery, or the controller can be re‑added — it is matched by MAC,
  so no duplicate is created.
- **Discovery after renaming.** Discovery matches mDNS names beginning with `ooly`. A
  controller renamed away from that prefix must be added manually by IP.
- **Incorrect control shown.** Set the correct controller type via the reconfigure flow.

## Development

`scripts/deploy.sh` synchronises `custom_components/ooly/` to a Home Assistant instance
over SSH and restarts it:

```sh
OOLY_HA_HOST=root@192.168.0.10 ./scripts/deploy.sh
```

It requires the Advanced SSH & Web Terminal add‑on (for `rsync` and the `ha` CLI) and SSH
key authentication; see `./scripts/deploy.sh --help` for options.

Linting and tests run in CI (ruff, hassfest, HACS validation, pytest) and locally:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check .
```

## License

Released under the [MIT License](LICENSE).
