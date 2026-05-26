"""SCSCL register metadata + mode dispatch table + pure helpers for the TUI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ============================================================================
# Register metadata
# ============================================================================


@dataclass
class RegDef:
    name: str
    addr: int
    length: int
    rw: bool
    live: bool = False
    description: str = ""
    units: str = ""
    min_value: int = 0
    max_value: Optional[int] = None
    options: Optional[dict[int, str]] = None

    @property
    def max(self) -> int:
        if self.max_value is not None:
            return self.max_value
        return (1 << (8 * self.length)) - 1


@dataclass(frozen=True)
class ModelProfile:
    name: str
    display_name: str
    model_numbers: tuple[int, ...]
    registers: list[RegDef]


COMMON_REGISTERS: list[RegDef] = [
    RegDef(
        "present_position",
        56,
        2,
        rw=False,
        live=True,
        description="Current position. 10-bit, 0-1023 (512 = center, ~0.293 deg/step).",
        units="steps",
        max_value=1023,
    ),
    RegDef(
        "goal_position",
        42,
        2,
        rw=True,
        live=True,
        description="Target position, 0-1023 over the configured angle range.",
        units="steps",
        max_value=1023,
    ),
    RegDef(
        "present_speed",
        58,
        2,
        rw=False,
        live=True,
        description="Current speed. SCSCL sign-magnitude (bit 10 = reverse).",
        min_value=-1023,
        max_value=1023,
    ),
    RegDef(
        "goal_speed",
        46,
        2,
        rw=True,
        description=(
            "Position mode: max speed cap. Wheel mode: signed velocity, "
            "bit 10 = reverse direction."
        ),
        min_value=-1023,
        max_value=1023,
    ),
    RegDef(
        "present_load",
        60,
        2,
        rw=False,
        live=True,
        description="Current load. SCSCL sign-magnitude, 0-1023 ~= 0-100%.",
        units="raw",
        min_value=-1023,
        max_value=1023,
    ),
    RegDef(
        "present_voltage",
        62,
        1,
        rw=False,
        live=True,
        description="Supply voltage.",
        units="x0.1 V",
    ),
    RegDef(
        "present_temperature",
        63,
        1,
        rw=False,
        live=True,
        description="Motor temperature.",
        units="degC",
    ),
    RegDef(
        "status",
        65,
        1,
        rw=False,
        live=True,
        description="Error flags: voltage, angle, overheat, overcurrent, overload.",
    ),
    RegDef(
        "moving",
        66,
        1,
        rw=False,
        live=True,
        description="Is the motor in motion right now?",
        options={0: "stopped", 1: "moving"},
    ),
    RegDef(
        "torque_enable",
        40,
        1,
        rw=True,
        live=True,
        description="Enable motor torque (holds position / drives speed).",
        options={0: "off", 1: "on"},
    ),
    RegDef(
        "goal_time",
        44,
        2,
        rw=True,
        description="Time-based move duration. Keep 0 to use goal_speed instead.",
        units="raw",
    ),
    RegDef(
        "lock",
        48,
        1,
        rw=True,
        description="SCSCL EEPROM write-lock. Auto-managed on EEPROM writes.",
        options={0: "unlocked", 1: "locked"},
    ),
    RegDef(
        "min_angle_limit",
        9,
        2,
        rw=True,
        description="Lower position limit. Set BOTH limits to 0 for wheel mode.",
        units="steps",
        max_value=1023,
    ),
    RegDef(
        "max_angle_limit",
        11,
        2,
        rw=True,
        description="Upper position limit. Set BOTH limits to 0 for wheel mode.",
        units="steps",
        max_value=1023,
    ),
    RegDef(
        "max_torque_limit",
        16,
        2,
        rw=True,
        description="Persistent max torque output (0-1023 ~= 0-100%).",
        units="raw",
        max_value=1023,
    ),
    RegDef(
        "p_coefficient",
        21,
        1,
        rw=True,
        description="Position-loop P gain. Higher = stiffer, may oscillate.",
        max_value=254,
    ),
    RegDef(
        "i_coefficient",
        23,
        1,
        rw=True,
        description="Position-loop I gain. Kills steady-state error.",
        max_value=254,
    ),
    RegDef(
        "d_coefficient",
        22,
        1,
        rw=True,
        description="Position-loop D gain. Damps oscillation.",
        max_value=254,
    ),
    RegDef(
        "minimum_startup_force",
        24,
        2,
        rw=True,
        description="Minimum force before motor starts moving.",
    ),
    RegDef("cw_dead_zone", 26, 1, rw=True, description="Clockwise position deadband."),
    RegDef(
        "ccw_dead_zone",
        27,
        1,
        rw=True,
        description="Counter-clockwise position deadband.",
    ),
    RegDef(
        "max_temperature_limit",
        13,
        1,
        rw=True,
        description="Motor shuts down above this temperature.",
        units="degC",
        max_value=100,
    ),
    RegDef(
        "max_voltage_limit",
        14,
        1,
        rw=True,
        description="Shutdown above this voltage.",
        units="x0.1 V",
    ),
    RegDef(
        "min_voltage_limit",
        15,
        1,
        rw=True,
        description="Shutdown below this voltage.",
        units="x0.1 V",
    ),
    RegDef("return_delay", 7, 1, rw=True, description="Reply delay in 2-us units."),
    RegDef(
        "response_status_level",
        8,
        1,
        rw=True,
        description="0=PING only, 1=READ only, 2=all instructions.",
        options={0: "0: ping only", 1: "1: read only", 2: "2: all"},
    ),
    RegDef(
        "id",
        5,
        1,
        rw=True,
        description=(
            "Motor ID. 0-253 (254 broadcast). "
            "Bus is rescanned automatically on change."
        ),
        max_value=253,
    ),
    RegDef(
        "baud_index",
        6,
        1,
        rw=True,
        description="Serial baud-rate index. Servo switches baud immediately on write.",
        options={
            0: "0: 1,000,000",
            1: "1: 500,000",
            2: "2: 250,000",
            3: "3: 128,000",
            4: "4: 115,200",
            5: "5: 76,800",
            6: "6: 57,600",
            7: "7: 38,400",
        },
    ),
]


SCS0009_REGISTERS: list[RegDef] = COMMON_REGISTERS
SCS0043_UNPOPULATED_REGISTERS = {
    "present_voltage",
    "present_current",
    "max_voltage_limit",
    "min_voltage_limit",
}

SCS0043_REGISTERS: list[RegDef] = [
    *[reg for reg in COMMON_REGISTERS if reg.name not in SCS0043_UNPOPULATED_REGISTERS][
        :6
    ],
    RegDef(
        "virtual_position",
        67,
        2,
        rw=False,
        live=True,
        description="Secondary/virtual position feedback observed on SCS0043.",
        units="steps",
        max_value=1023,
    ),
    *[reg for reg in COMMON_REGISTERS if reg.name not in SCS0043_UNPOPULATED_REGISTERS][
        6:
    ],
]

# model_numbers are the natural u16 values returned by `read_model` (register 3,
# big-endian on the wire). SCS0043 observed = 1290 (0x050A). The 5 for SCS0009
# is unverified — DEFAULT_MODEL is also scs0009, so a wrong value here would
# be masked by the fallback in `model_from_number`.
MODEL_PROFILES: dict[str, ModelProfile] = {
    "scs0009": ModelProfile("scs0009", "SCS0009", (5,), SCS0009_REGISTERS),
    "scs0043": ModelProfile("scs0043", "SCS0043", (1290,), SCS0043_REGISTERS),
}
MODEL_BY_NUMBER: dict[int, str] = {
    number: profile.name
    for profile in MODEL_PROFILES.values()
    for number in profile.model_numbers
}

DEFAULT_MODEL = "scs0009"
REGISTERS: list[RegDef] = MODEL_PROFILES[DEFAULT_MODEL].registers
REG_BY_NAME: dict[str, RegDef] = {r.name: r for r in REGISTERS}


def profile_for_model(model: str | None) -> ModelProfile:
    return MODEL_PROFILES.get(model or DEFAULT_MODEL, MODEL_PROFILES[DEFAULT_MODEL])


def model_from_number(model_number: int | None) -> str:
    return MODEL_BY_NUMBER.get(model_number or -1, DEFAULT_MODEL)


def registers_for_model(model: str | None) -> list[RegDef]:
    return profile_for_model(model).registers


def reg_by_name_for_model(model: str | None) -> dict[str, RegDef]:
    return {r.name: r for r in registers_for_model(model)}


EEPROM_END_ADDR = 27
LOCK_ADDR = 48
STATUS_ADDR = 65
TORQUE_ENABLE_ADDR = 40
GOAL_POSITION_ADDR = 42
GOAL_SPEED_ADDR = 46
PRESENT_POSITION_ADDR = 56
PRESENT_SPEED_ADDR = 58
PRESENT_LOAD_ADDR = 60
PRESENT_CURRENT_ADDR = 69
BROADCAST_ID = 254

# Bulk-read spans
EEPROM_BLOCK_START = 0
EEPROM_BLOCK_LEN = 28  # addresses 0-27
SRAM_BLOCK_START = 40
SRAM_BLOCK_LEN = 31  # addresses 40-70


# ============================================================================
# SCSCL status register bit decode (Feetech; best-effort shared layout)
# ============================================================================


STATUS_BITS: list[tuple[int, str, str]] = [
    # (mask, short, long)
    (0x01, "VOLT", "voltage out of range"),
    (0x02, "ANGLE", "angle limit exceeded"),
    (0x04, "HOT", "overheat"),
    (0x08, "CURR", "overcurrent"),
    (0x20, "OVLD", "overload"),
]


def decode_status(raw: int) -> tuple[list[str], list[str]]:
    """Return (short tags, long descriptions) for the set bits."""
    short, long = [], []
    for mask, s, l in STATUS_BITS:
        if raw & mask:
            short.append(s)
            long.append(l)
    return short, long


# ============================================================================
# Mode dispatch
# ============================================================================


MODE_POSITION = 0
MODE_WHEEL = 1


@dataclass
class ModeControl:
    label: str
    placeholder: str
    target: str  # "position" or "speed"
    signed: bool
    min_val: int
    max_val: int
    nudge_scale: int
    pretty_name: str


MODE_CONTROLS: dict[int, ModeControl] = {
    MODE_POSITION: ModeControl(
        label="goal:",
        placeholder="0-1023",
        target="position",
        signed=False,
        min_val=0,
        max_val=1023,
        nudge_scale=1,
        pretty_name="position (servo)",
    ),
    MODE_WHEEL: ModeControl(
        label="speed:",
        placeholder="-1023..1023 (signed)",
        target="speed",
        signed=True,
        min_val=-1023,
        max_val=1023,
        nudge_scale=5,
        pretty_name="wheel (continuous)",
    ),
}


def mode_ctrl(mode: int) -> ModeControl:
    return MODE_CONTROLS.get(mode, MODE_CONTROLS[MODE_POSITION])


def derive_mode(min_angle: int, max_angle: int) -> int:
    """SCSCL wheel mode is selected by setting both angle limits to 0."""
    return MODE_WHEEL if min_angle == 0 and max_angle == 0 else MODE_POSITION


# ============================================================================
# Byte / sign-magnitude helpers
# ============================================================================


def bytes_to_uint(b: bytes | list[int]) -> int:
    return int.from_bytes(bytes(b), byteorder="big", signed=False)


def uint_to_bytes(v: int, length: int) -> list[int]:
    return list(v.to_bytes(length, "big", signed=False))


def word_be(buf: bytes | list[int], off: int) -> int:
    return int.from_bytes(bytes(buf[off : off + 2]), "big", signed=False)


def word_be_signed_bit10(buf: bytes | list[int], off: int) -> int:
    raw = word_be(buf, off)
    mag = raw & 0x03FF
    return -mag if raw & 0x0400 else mag


def speed_signed_to_raw(signed: int) -> int:
    mag = abs(signed) & 0x03FF
    return mag | (0x0400 if signed < 0 else 0)


def speed_raw_to_signed(raw: int) -> int:
    mag = raw & 0x03FF
    return -mag if (raw & 0x0400) else mag


# ============================================================================
# Last-port memory
# ============================================================================


_STATE_FILE = Path.home() / ".cache" / "scs-suite" / "last.json"


def load_last_port() -> Optional[tuple[str, int]]:
    try:
        data = json.loads(_STATE_FILE.read_text())
        return (data["port"], int(data["baud"]))
    except Exception:
        return None


def save_last_port(port: str, baud: int) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({"port": port, "baud": baud}))
    except Exception:
        pass


# ============================================================================
# Baud-rate presets
# ============================================================================


BAUD_OPTIONS = [500_000, 1_000_000, 250_000, 128_000, 115_200, 76_800, 57_600, 38_400]
