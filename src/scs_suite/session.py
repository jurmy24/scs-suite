"""Shared state for the interactive menu.

When a user runs ``scs`` we open the serial port and scan
the bus once, then pass this ``Session`` to each command they pick. Commands
invoked directly from the shell (``scs test --port ...``) bypass all of this
and create their own one-shot bus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import motor as m


@dataclass
class Session:
    port: str
    baud: int
    bus: m.ScsController
    ids: list[int] = field(default_factory=list)
    motor_models: dict[int, str] = field(default_factory=dict)
    controller_model: str = "scs0009"
    max_motors: Optional[int] = None

    def rescan(self, progress_callback=None) -> list[int]:
        """Re-ping the bus and refresh the cached ID list."""
        self.ids = m.scan_ids(
            self.bus,
            progress_callback=progress_callback,
            max_motors=self.max_motors,
        )
        self.motor_models = {sid: m.detect_model(self.bus, sid) for sid in self.ids}
        return self.ids

    def close(self) -> None:
        # rustypot drops the port on Python GC; explicit break of the ref
        # just hastens it.
        self.bus = None  # type: ignore[assignment]


def open_session(
    port: str,
    baud: int,
    max_motors: Optional[int] = None,
    progress_callback=None,
) -> Session:
    session = Session(
        port=port,
        baud=baud,
        bus=m.open_bus(port=port, baudrate=baud),
        max_motors=max_motors,
    )
    session.rescan(progress_callback=progress_callback)
    if not session.ids:
        return session

    controller_model = session.motor_models.get(session.ids[0], "scs0009")
    if controller_model == session.controller_model:
        return session

    # Different controller class needed. Reopen the bus, but reuse the IDs
    # and models we already discovered — the motors on the wire don't
    # change just because we reopen the serial port.
    prev_ids = session.ids
    prev_models = session.motor_models
    session.close()
    return Session(
        port=port,
        baud=baud,
        bus=m.open_bus(port=port, baudrate=baud, model=controller_model),
        ids=prev_ids,
        motor_models=prev_models,
        controller_model=controller_model,
        max_motors=max_motors,
    )
