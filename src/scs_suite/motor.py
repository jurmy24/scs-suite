"""High-level SCSCL motor helpers backed by rustypot.

All multi-byte SCS registers are big-endian on the wire. The rustypot bindings
declare them with the ``BigEndian_u16`` conversion, so we call the non-``_raw_``
accessors (``read_present_position`` etc.) — those return the natural register
value (0..1023). The ``read_raw_*`` variants exist but return byte-swapped
bytes and should not be used here.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Optional, TypeAlias

from rustypot import Scs0009PyController, Scs0043PyController

from .tui_meta import model_from_number


# Raw position range for SCSCL servos (10-bit, ~0.293 deg/step).
POSITION_MIN = 0
POSITION_MAX = 1023


Controller: TypeAlias = Scs0009PyController | Scs0043PyController
CONTROLLERS: dict[str, type[Controller]] = {
    "scs0009": Scs0009PyController,
    "scs0043": Scs0043PyController,
}


def _first(result: Any) -> Any:
    """rustypot per-ID reads return a single-element list; unwrap it."""
    if isinstance(result, list):
        return result[0]
    return result


def open_bus(
    port: str,
    baudrate: int,
    timeout_s: float = 0.05,
    model: str = "scs0009",
) -> Controller:
    """Open the serial bus.

    Default timeout is 50 ms: EEPROM writes can take 3-5 ms of cell
    programming plus USB adapter latency (up to ~16 ms on CH340/FTDI),
    so shorter timeouts spuriously fire on writes that actually succeed.
    Full-range scans are still well under 15 s at this setting.
    """
    cls = CONTROLLERS[model] if model in CONTROLLERS else Scs0009PyController
    return cls(serial_port=port, baudrate=baudrate, timeout=timeout_s)


def scan_ids(
    bus: Controller,
    id_range: range = range(1, 254),
    progress_callback=None,
    max_motors: Optional[int] = None,
) -> list[int]:
    """Ping every ID in `id_range`; return the ones that reply.

    If ``max_motors`` is given, stop scanning as soon as that many motors
    have responded. This is what saves you ~50 ms per remaining ID when
    you already know how many motors are on the bus.
    """
    found: list[int] = []
    for sid in id_range:
        if progress_callback is not None:
            progress_callback(sid)
        try:
            if bus.ping(sid):
                found.append(sid)
                if max_motors is not None and len(found) >= max_motors:
                    return found
        except (RuntimeError, OSError):
            # Timeout / framing error = no motor at this ID.
            pass
    return found


def detect_model(bus: Controller, servo_id: int) -> str:
    """Return the SCS model profile name for a responding servo."""
    try:
        return model_from_number(_first(bus.read_model(servo_id)))
    except Exception:
        return "unknown"


@dataclass
class MotorState:
    """Snapshot of a motor's state at a point in time.

    ``present_voltage_v`` is None on models that don't expose the register
    (e.g. SCS0043).
    """

    servo_id: int
    present_position: int
    goal_position: int
    present_speed: int
    present_load: int
    present_temperature_c: int
    torque_enabled: bool
    max_torque_limit: int
    goal_speed: int
    min_angle: int
    max_angle: int
    p_gain: int
    i_gain: int
    d_gain: int
    moving: bool
    present_voltage_v: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_state(bus: Controller, servo_id: int) -> MotorState:
    voltage_raw = (
        _first(bus.read_present_voltage(servo_id))
        if hasattr(bus, "read_present_voltage")
        else None
    )
    return MotorState(
        servo_id=servo_id,
        present_position=_first(bus.read_present_position(servo_id)),
        goal_position=_first(bus.read_goal_position(servo_id)),
        present_speed=_first(bus.read_present_speed(servo_id)),
        present_load=_first(bus.read_present_load(servo_id)),
        present_temperature_c=_first(bus.read_present_temperature(servo_id)),
        torque_enabled=_first(bus.read_torque_enable(servo_id)),
        max_torque_limit=_first(bus.read_max_torque_limit(servo_id)),
        goal_speed=_first(bus.read_goal_speed(servo_id)),
        min_angle=_first(bus.read_min_angle_limit(servo_id)),
        max_angle=_first(bus.read_max_angle_limit(servo_id)),
        p_gain=_first(bus.read_p_coefficient(servo_id)),
        i_gain=_first(bus.read_i_coefficient(servo_id)),
        d_gain=_first(bus.read_d_coefficient(servo_id)),
        moving=_first(bus.read_moving(servo_id)),
        present_voltage_v=None if voltage_raw is None else voltage_raw / 10.0,
    )


def set_torque(bus: Controller, servo_id: int, enabled: bool) -> None:
    bus.write_torque_enable(servo_id, enabled)


def move_to(
    bus: Controller,
    servo_id: int,
    goal_raw: int,
    speed_raw: int = 300,
) -> None:
    """Commands an absolute position move in speed-based mode."""
    goal_raw = max(POSITION_MIN, min(POSITION_MAX, goal_raw))
    # goal_time must be 0 for speed-based motion; otherwise goal_speed is ignored.
    bus.write_goal_time(servo_id, 0)
    bus.write_goal_speed(servo_id, speed_raw)
    bus.write_goal_position(servo_id, goal_raw)


def read_present_position(bus: Controller, servo_id: int) -> int:
    return _first(bus.read_present_position(servo_id))


def wait_until_stopped(
    bus: Controller,
    servo_id: int,
    timeout_s: float = 3.0,
    poll_s: float = 0.04,
    tol_steps: int = 2,
    stable_ms: int = 250,
    warmup_ms: int = 300,
) -> bool:
    """Wait until the motor's position stops changing.

    The ``moving`` register alone is unreliable right after a goal write —
    it can read 0 before the servo has processed the new target, so a naive
    loop returns immediately. Instead we sleep a short ``warmup_ms`` for the
    servo to latch the new goal, then watch ``present_position`` and declare
    "stopped" once it's within ``tol_steps`` for ``stable_ms`` in a row.
    """
    time.sleep(warmup_ms / 1000.0)

    deadline = time.monotonic() + timeout_s
    last_pos = read_present_position(bus, servo_id)
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        pos = read_present_position(bus, servo_id)
        if abs(pos - last_pos) > tol_steps:
            stable_since = time.monotonic()
        elif (time.monotonic() - stable_since) * 1000 >= stable_ms:
            return True
        last_pos = pos
    return False
