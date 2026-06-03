# Changelog

## 0.2.0

First public release.

- **Device type per controller** — tunable white (CCT), colour (RGB), or colour + white
  (RGB + CCT), chosen on add and changeable later via **Reconfigure**.
- **Native colour temperature** sent to the firmware as `cct_k` (no channel maths); RGB and
  white are interlocked so the more-info card never "jumps" between modes.
- **Smooth transitions** (`tt_ms`) and an **optimistic UI** with background polling.
- **Resilient writes** — transient `503 BUSY` and the post-boot `403 BOOT_NOT_CONFIRMED`
  write-lock are retried automatically (honouring `Retry-After`).
- **mDNS discovery**, **stable MAC-based identity** (survives IP changes), and a
  **tunable polling interval** (Reconfigure).
- Device-reported colour-temperature range read from `/config/get`.
