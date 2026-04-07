"""Midea IR protocol encoder for RG56 Remote.

Encodes climate state into raw IR timings compatible with Home Assistant's
infrared building block (ESPHome IR proxy).

Packet structure:
  Climate (type 0xA1, 6 bytes):
    byte[0] = 0xA1
    byte[1] = power(bit7) | sleep(bit6) | fix(bit5) | fan_msb(bit4) | fan_lsb(bit3) | mode(bits2-0)
    byte[2] = 0x40 | (2*(temp-17)+1)  -- or 0x5F for FAN_ONLY
    byte[3] = 0xFF
    byte[4] = varies (see _COOL_AUTO_TABLE and _encode_b4)
    byte[5] = checksum (empirical from ESPHome captures)

  Special (type 0xA2, 5 bytes): pre-computed including checksum.
  Follow-Me (type 0xA4, 5 bytes).

Byte[1] encoding (confirmed from ESPHome frame captures):
  mode bits(2-0): COOL=000, HEAT_COOL=010, DRY=001, FAN_ONLY=100
  fan bits(4-3):  AUTO=00, LOW=01, MEDIUM=10, HIGH=11
  fix(bit5)=1:    only for COOL+AUTO and FAN_ONLY+AUTO
  sleep(bit6)=1:  SLEEP preset
  power(bit7)=1:  ON

Carrier: 38 kHz
Timing: header 4480/4480us, bit-1 560/1680us, bit-0 560/560us
Frame gap: 560us mark + 5600us space
Frame2 = bitwise complement of frame1 (Midea protocol standard)
"""
from __future__ import annotations

from infrared_protocols import Command, Timing

MIDEA_FREQUENCY_HZ = 38_000

# Timing constants (us)
_HEADER_HIGH = 4480
_HEADER_LOW  = 4480
_BIT_HIGH    = 560
_ONE_LOW     = 1680
_ZERO_LOW    = 560
_GAP_HIGH    = 560
_GAP_LOW     = 5600

# Mode bits (bits 2-0 of byte[1])
_MODE_COOL = 0   # 000
_MODE_HC   = 2   # 010  (heat_cool)
_MODE_DRY  = 1   # 001
_MODE_FAN  = 4   # 100

# Fan bits (bits 4-3 of byte[1])
_FAN_AUTO = 0
_FAN_LOW  = 1
_FAN_MED  = 2
_FAN_HIGH = 3

_TEMP_MIN = 17
_TEMP_MAX = 30


def _encode_b1(power: bool, mode: int, fan: int, sleep: bool = False) -> int:
    pwr     = 1 if power else 0
    slp     = 1 if (sleep and power) else 0
    fix     = 1 if (power and mode in (_MODE_COOL, _MODE_FAN) and fan == _FAN_AUTO) else 0
    fan_msb = (fan >> 1) & 1
    fan_lsb = fan & 1
    return (pwr << 7) | (slp << 6) | (fix << 5) | (fan_msb << 4) | (fan_lsb << 3) | mode


def _encode_b2(temp: float, mode: int, power: bool, last_temp: float = 24.0) -> int:
    if not power:
        t = max(_TEMP_MIN, min(_TEMP_MAX, int(round(last_temp))))
        return 0x40 | (2 * (t - _TEMP_MIN) + 1)
    if mode == _MODE_FAN:
        return 0x5F
    t = max(_TEMP_MIN, min(_TEMP_MAX, int(round(temp))))
    return 0x40 | (2 * (t - _TEMP_MIN) + 1)


# Empirical (b4, b5) for COOL/AUTO keyed by temperature (degrees C).
# Captured directly from ESPHome IR logs (frame1 bit extraction).
_COOL_AUTO_TABLE: dict[int, tuple[int, int]] = {
    17: (0xFE, 0xDC),
    18: (0xFF, 0x6F),
    19: (0xFF, 0x6C),
    20: (0xFE, 0xD4),
    21: (0xFE, 0xD4),
    22: (0xFE, 0xD6),
    23: (0xFE, 0xD0),
    24: (0xFE, 0xD2),
    25: (0xFE, 0xCC),
    26: (0xFE, 0xCE),
    27: (0xFE, 0xCA),
    28: (0xFE, 0xC8),
    29: (0xFE, 0xC6),   # interpolated
    30: (0xFE, 0xC6),
}

# Empirical (b4, b5) for other mode/fan combos keyed by (b1, b2).
# b5 values marked with * are from 47-bit captures (bit0 may be off by 1).
_OTHER_TABLE: dict[tuple[int, int], tuple[int, int]] = {
    (0x88, 0x47): (0xFE, 0xA2),  # COOL/Low/24
    (0x90, 0x47): (0xFE, 0x48),  # COOL/Med/24
    (0x98, 0x4F): (0xFD, 0x02),  # COOL/High/24  *
    (0x82, 0x45): (0xFE, 0xB2),  # HC/Auto/22    *
    (0x82, 0x47): (0xFE, 0xBA),  # HC/Auto/24 (note: b2=0x47=20deg slot)
    (0x81, 0x47): (0xFE, 0xB0),  # DRY/Auto/24   *
    (0xA4, 0x5F): (0xFE, 0xF4),  # FAN/Auto      *
    (0xE0, 0x4F): (0xFE, 0x12),  # COOL+SLEEP/Auto/24 (Sleep preset)
    (0x02, 0x4F): (0xFF, 0xB4),  # OFF (last temp=24)
}


def _lookup_b4_b5(b1: int, b2: int) -> tuple[int, int]:
    """Return (b4, b5) from empirical tables, or best-effort fallback."""
    # COOL/AUTO (b1 = 0xA0, or 0xE0 with sleep)
    if (b1 & 0x9F) == 0x80 and (b1 & 0x07) == 0:  # mode=COOL, fan=AUTO
        t_offset = (b2 - 0x41) // 2  # b2 = 0x40|(2*offset+1)
        temp = _TEMP_MIN + t_offset
        if temp in _COOL_AUTO_TABLE:
            return _COOL_AUTO_TABLE[temp]
    # Other modes
    if (b1, b2) in _OTHER_TABLE:
        return _OTHER_TABLE[(b1, b2)]
    # Fallback: determine b4 from power/fan/mode and use 0x00 for b5
    power   = bool(b1 >> 7)
    fan     = (b1 >> 3) & 3
    mode    = b1 & 7
    if not power:
        b4 = 0xFF
    elif fan == _FAN_HIGH and mode == _MODE_COOL:
        b4 = 0xFD
    else:
        b4 = 0xFE
    return b4, 0x00


# IR encoding helpers
def _bit_timing(bit: int) -> Timing:
    return Timing(high_us=_BIT_HIGH, low_us=_ONE_LOW if bit else _ZERO_LOW)


def _byte_timings(byte_val: int) -> list[Timing]:
    return [_bit_timing((byte_val >> (7 - i)) & 1) for i in range(8)]


def _frame(packet: list[int]) -> list[Timing]:
    t: list[Timing] = [Timing(high_us=_HEADER_HIGH, low_us=_HEADER_LOW)]
    for b in packet:
        t.extend(_byte_timings(b))
    return t


def _complement(packet: list[int]) -> list[int]:
    return [(~b) & 0xFF for b in packet]


def _build_timings(packet: list[int]) -> list[Timing]:
    """Build: frame1 + inter-frame gap + frame2 (= ~frame1) + trailing mark."""
    gap   = [Timing(high_us=_GAP_HIGH, low_us=_GAP_LOW)]
    trail = [Timing(high_us=_BIT_HIGH, low_us=0)]
    return _frame(packet) + gap + _frame(_complement(packet)) + trail


# Public Command classes

class MideaClimateCommand(Command):
    """Encodes a full AC climate state as Midea IR timings.

    Parameters
    ----------
    power:       True = on, False = off
    mode:        "cool" | "heat_cool" | "dry" | "fan_only"
    target_temp: setpoint in °C (17-30)
    fan_mode:    "auto" | "low" | "medium" | "high"
    sleep:       True = SLEEP preset active (sets bit6 in b1)
    last_temp:   remembered temperature used when powering off
    """

    _MODE_MAP = {
        "cool":      _MODE_COOL,
        "heat_cool": _MODE_HC,
        "dry":       _MODE_DRY,
        "fan_only":  _MODE_FAN,
    }
    _FAN_MAP = {
        "auto":   _FAN_AUTO,
        "low":    _FAN_LOW,
        "medium": _FAN_MED,
        "high":   _FAN_HIGH,
    }

    def __init__(
        self,
        *,
        power: bool,
        mode: str,
        target_temp: float,
        fan_mode: str,
        sleep: bool = False,
        last_temp: float = 24.0,
    ) -> None:
        super().__init__(modulation=MIDEA_FREQUENCY_HZ, repeat_count=0)
        self._power      = power
        self._mode       = mode
        self._target_temp = target_temp
        self._fan_mode   = fan_mode
        self._sleep      = sleep
        self._last_temp  = last_temp

    def get_raw_timings(self) -> list[Timing]:
        power    = self._power
        mode_val = self._MODE_MAP.get(self._mode, _MODE_HC)
        fan_val  = self._FAN_MAP.get(self._fan_mode, _FAN_AUTO)

        b0 = 0xA1
        b1 = _encode_b1(power, mode_val, fan_val, self._sleep)
        b2 = _encode_b2(self._target_temp, mode_val, power, self._last_temp)
        b3 = 0xFF
        b4, b5 = _lookup_b4_b5(b1, b2)

        return _build_timings([b0, b1, b2, b3, b4, b5])


class MideaRawCommand(Command):
    """Sends a pre-built 5-byte special command (checksum already in byte[4])."""

    def __init__(self, packet: list[int]) -> None:
        super().__init__(modulation=MIDEA_FREQUENCY_HZ, repeat_count=0)
        assert len(packet) == 5, "Special packet must be exactly 5 bytes"
        self._packet = list(packet)

    def get_raw_timings(self) -> list[Timing]:
        return _build_timings(self._packet)


class MideaFollowMeCommand(Command):
    """Follow-Me room temperature report (sent every 3 minutes).

    Parameters
    ----------
    temp_celsius: measured room temperature
    offset:       user-configurable offset (default 0)
    beep:         whether the AC beeps on receipt
    """

    def __init__(
        self,
        temp_celsius: float,
        offset: float = 0.0,
        beep: bool = False,
    ) -> None:
        super().__init__(modulation=MIDEA_FREQUENCY_HZ, repeat_count=0)
        raw = temp_celsius + offset
        self._temp_byte = max(0, min(0xFF, int(round(raw))))
        self._beep = beep

    def get_raw_timings(self) -> list[Timing]:
        beep_byte = 0xFF if self._beep else 0x7F
        # 0x48 = Celsius flag; byte[4] = temperature
        # Note: ESPHome's finalize() would add a 6th checksum byte.
        # We send 5 bytes; the complement frame provides error detection.
        packet = [0xA4, 0x82, 0x48, beep_byte, self._temp_byte]
        return _build_timings(packet)


# Pre-built singletons — exact byte sequences from ESPHome captures
# (byte[4] is the ESPHome-computed checksum, extracted from IR logs)
DEFLECTORS_POSITION = MideaRawCommand([0xA2, 0x01, 0xFF, 0xFF, 0xFB])
FRONT_PANEL_LIGHTS  = MideaRawCommand([0xA2, 0x08, 0xFF, 0xFF, 0xFB])
SELF_CLEAN          = MideaRawCommand([0xA2, 0x0D, 0xFF, 0xFF, 0xF7])
TURBO               = MideaRawCommand([0xA2, 0x09, 0xFF, 0xFF, 0xF7])
DEFLECTORS_SWING    = MideaRawCommand([0xA2, 0x02, 0xFF, 0xFF, 0xFD])

# Aliases used by climate.py and button.py
BOOST        = TURBO            # BOOST preset sends same code as Turbo button
SWING_TOGGLE = DEFLECTORS_SWING  # Swing vertical = toggle, same as DeflectorsSwing
