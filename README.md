# RG56 Remote — Home Assistant Custom Integration

Control your Midea air conditioner (RG56/BGEFU1-CA remote) from Home Assistant via infrared.

Built on the native [`infrared`](https://www.home-assistant.io/integrations/infrared/) building block introduced in HA 2026.4.

## Requirements

- Home Assistant **2026.4** or later
- An ESPHome device with IR transmitter already added to Home Assistant

## Entities created

| Platform | Entity | Notes |
|---|---|---|
| `climate` | RG56 Remote | Full climate control: mode, temperature, fan speed |
| `switch` | Follow Me Mode | Sends room temp to AC every 3 min via IR |
| `button` | Front Panel Lights | Toggle display lights |
| `button` | Deflectors Position | Step through deflector positions |
| `button` | Deflectors Swing | Toggle swing mode |
| `button` | Self Clean | Trigger self-clean cycle |
| `button` | Turbo | Toggle turbo mode |

## Follow Me mode

When enabled, the integration reads your chosen temperature sensor and sends the room temperature to the AC unit every 3 minutes via IR, allowing the AC to use that temperature instead of its internal sensor.
