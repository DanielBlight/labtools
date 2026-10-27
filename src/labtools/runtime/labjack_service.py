"""Narrow synchronous LabJack service, created/used/closed on its session worker.

Importing this module does not import native drivers or connect to instruments.
"""
from dataclasses import dataclass
from threading import get_ident

from labtools.runtime.cleanup import cleanup_actions
from labtools.runtime.mirror_backend import validate_target
from labtools.runtime.session import InstrumentSession


@dataclass(frozen=True)
class LabJackWiring:
    mirror_dio_pin: int = 2
    spad_gate_pin: int = 0

    def validate(self):
        # The LJTick-DAC uses two consecutive FIO/EIO lines. Preserve defaults.
        if type(self.mirror_dio_pin) is not int or not 0 <= self.mirror_dio_pin <= 14:
            raise ValueError("Mirror DIO must be an integer from 0 to 14")
        if type(self.spad_gate_pin) is not int or not 0 <= self.spad_gate_pin <= 15:
            raise ValueError("Gate pin must be an integer from 0 to 15")
        if self.spad_gate_pin in {self.mirror_dio_pin, self.mirror_dio_pin + 1}:
            raise ValueError("Gate pin must not overlap the mirror's two DIO lines")


class LabJackService:
    """Own one connection and its mirror/gate; expose no raw handles.

    Construct via open_labjack_service() on the owning session worker. No move
    or gate-open command is sent by this constructor. close() attempts gate-close
    and device-close independently, but never homes the mirror on disconnect.
    """

    def __init__(self, device, mirror, gate):
        self._device = device
        self._mirror = mirror
        self._gate = gate
        self._thread = get_ident()
        self._closed = False

    def _check(self):
        if get_ident() != self._thread:
            raise RuntimeError("LabJack service must run on its owning worker thread")
        if self._closed:
            raise RuntimeError("LabJack service is closed")

    def move(self, x_voltage, y_voltage):
        self._check()
        validate_target(x_voltage, y_voltage)
        self._mirror.move(x_voltage, y_voltage)

    def home(self):
        self._check()
        self._mirror.home()

    def open_gate(self):
        self._check()
        self._gate.open()

    def close_gate(self):
        self._check()
        self._gate.close()

    def close(self):
        if get_ident() != self._thread:
            raise RuntimeError("LabJack service must close on its owning worker thread")
        if self._closed:
            return
        try:
            with cleanup_actions(("gate close", self._gate.close),
                                 ("LabJack close", self._device.close)):
                pass
        finally:
            self._closed = True


def open_labjack_service(wiring=LabJackWiring(), *, device_factory=None,
                         mirror_factory=None, gate_factory=None):
    """Lazy real defaults; fake factories may be explicitly injected for tests.

    Factories must clean up their own constructor failures. Once a device has
    been returned here, subsequent wrapper-construction failures close it.
    """
    wiring.validate()
    if device_factory is None:
        from labtools.devices.labjack_u6 import LabJackU6
        device_factory = LabJackU6
    if mirror_factory is None:
        from labtools.devices.scanning_mirror import ScanningMirror
        mirror_factory = ScanningMirror
    if gate_factory is None:
        from labtools.devices.spad_gate import SPADGate
        gate_factory = SPADGate
    device = device_factory()
    gate = None
    try:
        mirror = mirror_factory(device, dio_pin=wiring.mirror_dio_pin)
        gate = gate_factory(device, pin=wiring.spad_gate_pin)
        return LabJackService(device, mirror, gate)
    except BaseException as exc:
        actions = [] if gate is None else [("partial gate close", gate.close)]
        actions.append(("partial LabJack close", device.close))
        for label, action in actions:
            try:
                action()
            except Exception as cleanup:
                exc.add_note(f"{label} failed: {cleanup!r}")
        raise


def create_labjack_session(wiring=LabJackWiring(), *, service_factory=None):
    """Create an unopened session. Real hardware opens only on the first call.

    Allow only argument-free home and gate-close after a fault. Home is a
    movement retained from existing map cleanup, not a universal safe position.
    """
    wiring.validate()
    factory = service_factory if service_factory is not None else lambda: open_labjack_service(wiring)
    return InstrumentSession({"labjack": factory},
        aliases={"mirror": "labjack", "gate": "labjack"},
        cleanup_methods={"labjack": ("home", "close_gate")})
