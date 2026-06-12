# HP/Aruba ProCurve — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/bjornar-isaksen/procurve-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/bjornar-isaksen/procurve-ha/actions/workflows/validate.yml)

Home Assistant integration for HP/Aruba ProCurve switches running **ArubaOS-Switch 16.x+**.

Communicates directly with the switch REST API — no cloud, no proxy.

## Supported models

All models running ArubaOS-Switch (firmware 16.08 or newer):

- HP 2530 series
- HP 2540 series (e.g. 2540-48G)
- HP 2920 series
- HP 2930F / 2930M
- HP 3810M
- Aruba 2930F / 2930M
- Aruba 3810M

## Features

### Sensors
- Per-port: RX/TX traffic (MB), link speed (Mbit/s), PoE power consumption (W)
- System: CPU usage, memory usage, temperature, uptime, total PoE draw, firmware version

### Binary sensors
- Per-port link status (up/down)
- Fan status, PSU status

### Switches (controls)
- Per PoE-port: enable/disable PoE
- Per port: enable/disable port (admin up/down)

### Buttons
- Restart switch

### Device trackers
- Connected devices (from MAC address table + ARP table)

## Installation via HACS

1. In HACS, go to **Integrations** → three-dot menu → **Custom repositories**
2. Add `https://github.com/bjornar-isaksen/procurve-ha` with category **Integration**
3. Search for "ProCurve" and install
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** and search for **HP/Aruba ProCurve**

## Manual installation

1. Copy the `custom_components/procurve` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

## Configuration

The integration is configured via the UI. You need:

| Field | Description | Default |
|---|---|---|
| Host | IP address or hostname of the switch | — |
| Port | HTTPS port | 443 |
| Username | Switch management username | manager |
| Password | Switch management password | — |
| Verify SSL | Verify the switch's TLS certificate | false |
| Scan interval | Polling interval in seconds | 30 |

## Requirements

- ArubaOS-Switch firmware **16.08** or newer
- REST API must be enabled on the switch (`web-management ssl`)
- A local management account (not RADIUS/TACACS)

## Enable REST API on the switch

```
web-management ssl
```

Or for HTTP (not recommended):
```
web-management plaintext
```

## License

MIT — see [LICENSE](LICENSE)
