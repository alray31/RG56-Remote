"""Midea IR protocol encoder.

Encodes climate state into 5-byte Midea IR packets and converts
to raw timings compatible with infrared_protocols.Command.

Packet structure (5 bytes + inverted checksum byte):
  Byte 0: 0xB2 (control type marker)
  Byte 1: mode + power + fan
  Byte 2: temperature (17-30°C → 0x00-0x0D)
  Byte 3: swing / sleep / turbo flags
  Byte 4: checksum = ~(byte0 ^ byte1 ^ byte2 ^ byte3)

Special packets (Follow Me, display, deflectors etc.) use 0xA2/0xA4 marker.

Carrier: 38 kHz
"""
from __future__ import annotations

from infrared_protocols import Command, Timing

MIDEA_FREQUENCY_HZ = 38_000

# Timing constants (µs)
_HEADER_HIGH = 4500
_HEADER_LOW = 4500
_BIT_HIGH = 560
_ONE_LOW = 1690
_ZERO_LOW = 560
_TRAILER_HIGH = 560
_TRAILER_LOW = 5220
_FRAME_GAP = 5000  # gap between the two identical frames

# Mode nibbles (upper nibble of byte 1)
_MODE_AUTO = 0x01
_MODE_COOL = 0x02
_MODE_DRY = 0x04
_MODE_HEAT = 0x08
_MODE_FAN = 0x00

# Fan speed nibbles (lower nibble of byte 1)
_FAN_AUTO = 0x00
_FAN_LOW = 0x06
_FAN_MEDIUM = 0x04
_FAN_HIGH = 0x02

# Temperature range
_TEMP_MIN = 17
_TEMP_MAX = 30


def _encode_byte(byte: int) -> list[Timing]:
    """Encode 8 bits MSB first."""
    result = []
    for i in range(7, -1, -1):
        bit = (byte >> i) & 1
        result.append(Timing(high_us=_BIT_HIGH, low_us=_ONE_LOW if bit else _ZERO_LOW))
    return result


def _build_packet(b0: int, b1: int, b2: int, b3: int) -> list[int]:
    """Build a 5-byte Midea packet with checksum."""
    checksum = (~(b0 ^ b1 ^ b2 ^ b3)) & 0xFF
    return [b0, b1, b2, b3, checksum]


def _packet_to_timings(packet: list[int]) -> list[Timing]:
    """Convert a 5-byte packet to IR timings."""
    timings: list[Timing] = [Timing(high_us=_HEADER_HIGH, low_us=_HEADER_LOW)]
    for byte in packet:
        timings.extend(_encode_byte(byte))
    timings.append(Timing(high_us=_TRAILER_HIGH, low_us=_TRAILER_LOW))
    return timings


class MideaClimateCommand(Command):
    """Midea IR climate command — encodes full AC state."""

    def __init__(
        self,
        *,
        power: bool,
        mode: str,
        target_temp: float,
        fan_mode: str,
        sleep: bool = False,
    ) -> None:
        super().__init__(modulation=MIDEA_FREQUENCY_HZ, repeat_count=0)
        self._power = power
        self._mode = mode
        self._target_temp = target_temp
        self._fan_mode = fan_mode
        self._sleep = sleep

    def get_raw_timings(self) -> list[Timing]:
        # Byte 0: always 0xB2 for control packets
        b0 = 0xB2

        # Byte 1: power(1) | mode(4) | fan(3)
        power_bit = 0x40 if self._power else 0x00
        mode_nibble = {
            "auto": _MODE_AUTO,
            "cool": _MODE_COOL,
            "dry": _MODE_DRY,
            "heat": _MODE_HEAT,
            "fan_only": _MODE_FAN,
        }.get(self._mode, _MODE_AUTO)
        fan_nibble = {
            "auto": _FAN_AUTO,
            "low": _FAN_LOW,
            "medium": _FAN_MEDIUM,
            "high": _FAN_HIGH,
        }.get(self._fan_mode, _FAN_AUTO)
        b1 = power_bit | (mode_nibble << 2) | fan_nibble

        # Byte 2: temperature (17=0x00 ... 30=0x0D), all bits set for fan-only
        if self._mode == "fan_only" or not self._power:
            b2 = 0xFF
        else:
            temp = max(_TEMP_MIN, min(_TEMP_MAX, int(round(self._target_temp))))
            b2 = temp - _TEMP_MIN

        # Byte 3: sleep flag
        b3 = 0x80 if self._sleep else 0x00

        packet = _build_packet(b0, b1, b2, b3)
        frame = _packet_to_timings(packet)

        # Midea sends the frame twice with a gap
        gap = [Timing(high_us=_TRAILER_HIGH, low_us=_FRAME_GAP)]
        return frame + gap + frame


class MideaRawCommand(Command):
    """Midea IR raw command — for special codes like Follow Me, display, turbo etc."""

    def __init__(self, code: list[int]) -> None:
        super().__init__(modulation=MIDEA_FREQUENCY_HZ, repeat_count=0)
        # code is the 4 meaningful bytes; checksum is added automatically
        assert len(code) == 5, "Midea raw code must be exactly 5 bytes"
        self._code = code

    def get_raw_timings(self) -> list[Timing]:
        frame = _packet_to_timings(self._code)
        gap = [Timing(high_us=_TRAILER_HIGH, low_us=_FRAME_GAP)]
        return frame + gap + frame


def make_follow_me_command(temp_celsius: float, beep: bool = False) -> MideaRawCommand:
    """Build a Follow Me command with the given room temperature."""
    temp_byte = max(0, min(0x3F, int(round(temp_celsius)) + 2))
    beep_byte = 0xFF if beep else 0x7F
    # 0x48 = Celsius flag, 0x68 = Fahrenheit flag
    code = [0xA4, 0x82, 0x48, beep_byte, temp_byte]
    return MideaRawCommand(code)


# Pre-built special commands matching the ESPHome YAML exactly
FRONT_PANEL_LIGHTS = MideaRawCommand([0xA2, 0x08, 0xFF, 0xFF, 0xFF])
DEFLECTORS_POSITION = MideaRawCommand([0xA2, 0x01, 0xFF, 0xFF, 0xFF])
SELF_CLEAN = MideaRawCommand([0xA2, 0x0D, 0xFF, 0xFF, 0xFF])
TURBO = MideaRawCommand([0xA2, 0x09, 0xFF, 0xFF, 0xFF])
DEFLECTORS_SWING = MideaRawCommand([0xA2, 0x02, 0xFF, 0xFF, 0xFF])
