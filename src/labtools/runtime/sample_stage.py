"""USB ANC350 sample stage: serialized, explicit commands and bounded DC ramps.

Axes are X=0, Z=1, Y=2. No native imports or connection until Connect.
"""

import math
import multiprocessing
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

AXES = (("X", 0), ("Z", 1), ("Y", 2))


def finite(value, low, high, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")  # noqa: TRY004 - preserve the numeric-validation ValueError contract
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return value


def _open_anc350(base, backend_error, usb_error):
    """Adapt only the verified pre-sync read, without editing site-packages."""
    import ast
    import inspect
    import textwrap

    def optional_boot_read(instrument, size):
        try:
            return instrument.read(size)
        except backend_error as error:
            cause = error.__cause__
            if not isinstance(cause, usb_error):
                raise
            message = str(cause).lower()
            if not all(token in message for token in ('libusb0-dll', '_usb_reap_async', 'timeout error')):
                raise
            # A quiet IN endpoint is allowed only before the sync request.
            return None

    original = base.__init__
    module = ast.parse(textwrap.dedent(inspect.getsource(original)))
    if len(module.body) != 1 or not isinstance(module.body[0], ast.FunctionDef):
        raise RuntimeError('Unrecognised ANC350 constructor; no USB connection attempted')
    init = module.body[0]
    expected = ast.parse('with self._close_on_error():\n    self.instr.flush_read()\n    self.instr.read(512)\n    self.set_value(0x000A, 0, 0)\n    self.get_hardware_id()\n    self.enable_updates(False)').body[0]
    blocks = [node for node in init.body if isinstance(node, ast.With)
              and ast.dump(node) == ast.dump(expected)]
    if len(blocks) != 1 or init.decorator_list or not init.args.args or not init.args.args or init.args.args[0].arg != 'self':
        raise RuntimeError('Unrecognised ANC350 startup sequence; no USB connection attempted')
    read = blocks[0].body[1]
    read.value = ast.Call(func=ast.Name(id='_optional_boot_read', ctx=ast.Load()),
                          args=[read.value.func.value, *read.value.args], keywords=[])
    calls = [node for node in ast.walk(init) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == 'super'
             and not node.args and not node.keywords]
    if len(calls) != 1 or original.__code__.co_freevars != ('__class__',):
        raise RuntimeError('Unrecognised ANC350 constructor; no USB connection attempted')
    calls[0].args = [ast.Name(id='_anc_base', ctx=ast.Load()), ast.Name(id='self', ctx=ast.Load())]
    namespace = {**original.__globals__, '_optional_boot_read': optional_boot_read, '_anc_base': base}
    # Compile a private constructor; the dependency and its module are unchanged.
    exec(compile(ast.fix_missing_locations(module), original.__code__.co_filename, 'exec'), namespace)  # noqa: S102
    adapted = type('LabtoolsANC350', (base,), {'__init__': namespace['__init__']})
    return adapted()


def _anc350_process(connection):
    """Own pylablib, PyUSB and libusb0 for exactly one connection lifetime."""
    device = None
    try:
        from pylablib.devices import Attocube

        from pylablib.devices.Attocube.base import AttocubeBackendError
        from usb.core import USBError

        device = _open_anc350(Attocube.ANC350, AttocubeBackendError, USBError)
        connection.send(("ready", None))
        while True:
            request = connection.recv()
            if request[0] == "close":
                break
            _kind, method, args, kwargs = request
            try:
                connection.send(("result", getattr(device, method)(*args, **kwargs)))
            except BaseException as error:  # noqa: BLE001 - child protocol must return driver failures
                connection.send(("error", type(error).__name__, str(error), traceback.format_exc()))
    except BaseException as error:  # noqa: BLE001 - child startup failure crosses process boundary
        try:
            connection.send(("startup-error", type(error).__name__, str(error), traceback.format_exc()))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if device is not None:
            try:
                device.close()
            except BaseException:  # noqa: BLE001, S110 - process exit is the final USB cleanup boundary
                pass
        connection.close()


class ANC350Process:
    """Fresh process per USB session so Disconnect releases all libusb0 state."""

    def __init__(self, *, startup_timeout=15.0, operation_timeout=35.0):
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_anc350_process, args=(child,), name="labtools-anc350-usb", daemon=True)
        process.start()
        child.close()
        self._connection = parent
        self._process = process
        self._operation_timeout = operation_timeout
        try:
            message = self._receive(startup_timeout, "ANC350 startup")
            if message[0] != "ready":
                self._raise_remote(message)
        except BaseException:
            self._terminate()
            raise

    def _receive(self, timeout, action):
        if not self._connection.poll(timeout):
            raise TimeoutError(f"{action} exceeded {timeout:g} seconds")
        try:
            return self._connection.recv()
        except EOFError as error:
            raise RuntimeError(f"{action} process exited unexpectedly") from error

    @staticmethod
    def _raise_remote(message):
        _kind, name, detail, remote = message
        error = RuntimeError(f"ANC350 {name}: {detail}")
        error.add_note("Remote ANC350 process traceback:\n" + remote)
        raise error

    def _call(self, method, *args, **kwargs):
        if not self._process.is_alive():
            raise RuntimeError("ANC350 USB process is not running")
        self._connection.send(("call", method, args, kwargs))
        message = self._receive(self._operation_timeout, method)
        if message[0] == "error":
            self._raise_remote(message)
        if message[0] != "result":
            raise RuntimeError(f"Unexpected ANC350 process reply: {message[0]}")
        return message[1]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self._call(name, *args, **kwargs)

    def _terminate(self):
        if self._process.is_alive():
            self._process.terminate()
        self._process.join(5)
        self._connection.close()

    def close(self):
        if self._process.is_alive():
            try:
                self._connection.send(("close",))
                self._process.join(10)
            except (BrokenPipeError, EOFError, OSError):
                pass
        if self._process.is_alive():
            self._terminate()
            raise RuntimeError("ANC350 close timed out; USB process was terminated")
        self._connection.close()


def native_factory():
    return ANC350Process()


class StageStopped(RuntimeError):
    pass


class SimulatedStage:
    """Explicit simulation only; never used as a fallback for USB errors."""

    def __init__(self):
        self.offset = [0.0] * 3
        self.position = [0.00335, 0.00274, 0.00138]
        self.voltage = [60.0, 30.0, 60.0]
        self.frequency = [200, 50, 200]
        self.enabled = [True] * 3

    def get_offset(self, axis):
        return self.offset[axis]

    def set_offset(self, axis, voltage):
        self.position[axis] += (voltage - self.offset[axis]) * 1e-8
        self.offset[axis] = voltage

    def get_position(self, axis):
        return self.position[axis]

    def get_voltage(self, axis):
        return self.voltage[axis]

    def set_voltage(self, axis, voltage):
        self.voltage[axis] = voltage

    def get_frequency(self, axis):
        return self.frequency[axis]

    def set_frequency(self, axis, freq):
        self.frequency[axis] = freq

    def is_connected(self, axis):
        return True

    def is_enabled(self, axis):
        return self.enabled[axis]

    def enable_axis(self, axis, enabled=True):
        self.enabled[axis] = enabled

    def get_status(self, axis):
        return []

    def check_limit(self, axis):
        return None

    def move_by_steps(self, axis, steps):
        self.position[axis] += steps * self.voltage[axis] * 1e-8

    def move_to(self, axis, position):
        self.position[axis] = position

    def is_target_reached(self, axis):
        return True

    def stop(self, axis):
        pass

    def close(self):
        pass


class SampleStage:
    """One connection/thread, one exclusive owner, no output changes on connect/close.

    Ownership is acquired before dispatch and held until the caller's cleanup.
    GUI callers also reserve the workspace optical path during manual commands.
    """

    def __init__(self, *, simulated=False, factory=None, realtime=True):
        self.simulated = simulated
        self.factory = factory or (SimulatedStage if simulated else native_factory)
        self.realtime = realtime or not simulated
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-anc350")
        self.lock = Lock()
        self.owner = None
        self.device = None
        self.stop_event = Event()
        self.closed = False
        self.fault = None

    @property
    def connected(self):
        return self.device is not None

    @property
    def busy(self):
        with self.lock:
            return self.owner is not None

    def claim(self):
        with self.lock:
            if self.closed or self.owner is not None:
                raise RuntimeError("Stage is closed or reserved by another operation")
            token = object()
            self.owner = token
            self.stop_event.clear()
            return token

    def release(self, token):
        with self.lock:
            if self.owner is not token:
                raise RuntimeError("Invalid stage reservation")
            self.owner = None

    def submit(self, token, command, **kwargs):
        with self.lock:
            if self.owner is not token or self.closed:
                raise RuntimeError("Stage operation requires its active reservation")
        return self.executor.submit(self._run, command, **kwargs)

    def call(self, token, command, **kwargs):
        return self.submit(token, command, **kwargs).result()

    def request_stop(self):
        self.stop_event.set()

    def check_stop(self, cancel=None):
        if self.stop_event.is_set() or (cancel is not None and cancel()):
            raise StageStopped("Stage stopped; holding the last applied DC offset")

    def wait(self, seconds, cancel=None):
        end = time.monotonic() + seconds
        while self.realtime and time.monotonic() < end:
            self.check_stop(cancel)
            self.stop_event.wait(min(.02, max(0, end - time.monotonic())))
        self.check_stop(cancel)

    def _ready(self, axis, *, moving=True):
        if not self.connected:
            raise RuntimeError("Connect the stage first")
        if isinstance(axis, bool) or not isinstance(axis, int) or axis not in (0, 1, 2):
            raise ValueError("Invalid stage axis")
        if not self.device.is_connected(axis=axis):
            raise RuntimeError("Stage axis is not connected")
        if moving:
            if self.fault:
                raise RuntimeError("Stage fault: disconnect/reconnect after inspecting the controller")
            if not self.device.is_enabled(axis=axis):
                raise RuntimeError("Enable the axis output explicitly before movement")
            status = self.device.get_status(axis=axis)
            if any(s in status for s in ("sens_err", "sens_disconn", "running")):
                raise RuntimeError(f"Stage axis not ready: {status}")

    def _ramp(self, axis, target, cancel=None):
        target = finite(target, 0, 60, "DC offset (V)")
        start = finite(self.device.get_offset(axis=axis), 0, 60, "Current DC offset (V)")
        if abs(start - target) < .001:
            return
        # 50 bounded updates over approximately 0.5 s plus USB overhead.
        for index in range(1, 51):
            self.check_stop(cancel)
            self.device.set_offset(axis=axis, voltage=start + (target - start) * index / 50)
            self.wait(.01, cancel)
        actual = float(self.device.get_offset(axis=axis))
        if not math.isfinite(actual) or abs(actual - target) > .02:
            raise RuntimeError(f"DC readback mismatch: requested {target:g} V, read {actual:g} V")

    def _step(self, axis, direction, cancel=None):
        if isinstance(direction, bool) or direction not in (-1, 1):
            raise ValueError("Step direction must be -1 or +1")
        self._ramp(axis, 0, cancel)
        self.check_stop(cancel)
        limit = self.device.check_limit(axis=axis)
        if limit == "both" or limit == ("fwd" if direction > 0 else "bwd"):
            raise RuntimeError(f"Stage end of travel: {limit}")
        finite(self.device.get_voltage(axis=axis), 0, 60, "Current step amplitude (V)")
        self.device.move_by_steps(axis=axis, steps=direction)
        self.wait(max(.05, 2 / max(1, self.device.get_frequency(axis=axis))), cancel)

    def snapshot(self):
        if not self.connected:
            return {"connected": False, "simulated": self.simulated}
        return {"connected": True, "simulated": self.simulated, "axes": {
            name: {"axis": axis, "position_m": float(self.device.get_position(axis=axis)),
                   "dc_v": float(self.device.get_offset(axis=axis)),
                   "amplitude_v": float(self.device.get_voltage(axis=axis)),
                   "frequency_hz": float(self.device.get_frequency(axis=axis)),
                   "enabled": bool(self.device.is_enabled(axis=axis)),
                   "connected": bool(self.device.is_connected(axis=axis)),
                   "status": list(self.device.get_status(axis=axis)),
                   "limit": self.device.check_limit(axis=axis)} for name, axis in AXES}}

    def _run(self, command, axis=1, value=None, cancel=None):
        if command == "connect":
            if self.device is None:
                self.device = self.factory()
                self.fault = None
            return self.snapshot()
        if command == "disconnect":
            if self.device is not None:
                # Drop the parent reference before close. The subprocess proxy
                # terminates its USB process on a close timeout, so reconnect can
                # always create a fresh process even if cleanup reports failure.
                device, self.device = self.device, None
                device.close()
                self.fault = None
            return self.snapshot()
        if command == "read":
            return self.snapshot()
        self._ready(axis, moving=command != "enable")
        self.check_stop(cancel)
        try:
            if command == "ramp":
                self._ramp(axis, value, cancel)
            elif command == "step":
                self._step(axis, value, cancel)
            elif command == "amplitude":
                self.device.set_voltage(axis=axis, voltage=finite(value, 0, 60, "Step amplitude (V)"))
            elif command == "frequency":
                self.device.set_frequency(axis=axis, freq=int(finite(value, 1, 2000, "Frequency (Hz)")))
            elif command == "enable":
                if not isinstance(value, bool):
                    raise ValueError("Output enable must be boolean")
                if value and not self.device.is_enabled(axis=axis):
                    target = finite(self.device.get_offset(axis=axis), 0, 60, "Stored DC offset (V)")
                    self.device.set_offset(axis=axis, voltage=0)
                    self.device.enable_axis(axis=axis, enabled=True)
                    self._ramp(axis, target, cancel)
                elif not value:
                    self.device.stop(axis=axis)
                    self._ramp(axis, 0, cancel)
                    self.device.enable_axis(axis=axis, enabled=False)
                if bool(self.device.is_enabled(axis=axis)) != value:
                    raise RuntimeError("Axis output readback did not match the requested state")
            elif command in ("absolute", "relative"):
                target = finite(value, -0.01, .01, "Position/distance (m)")
                if command == "relative":
                    target += float(self.device.get_position(axis=axis))
                self._ramp(axis, 0, cancel)
                self.device.move_to(axis=axis, position=target)
                try:
                    end = time.monotonic() + 30
                    while not self.device.is_target_reached(axis=axis):
                        if time.monotonic() > end:
                            raise TimeoutError("Stage positioning exceeded 30 seconds")
                        self.wait(.05, cancel)
                        status = self.device.get_status(axis=axis)
                        if any(s in status for s in ("sens_err", "sens_disconn", "limit")):
                            raise RuntimeError(f"Stage move stopped: {status}")
                finally:
                    self.device.stop(axis=axis)
            else:
                raise ValueError("Unknown stage command")
            return self.snapshot()
        except StageStopped:
            raise
        except Exception as error:
            self.fault = str(error)
            raise

    def shutdown(self):
        if self.busy:
            raise RuntimeError("Wait for stage operation cleanup before shutdown")
        if self.closed:
            return
        token = self.claim()
        try:
            self.call(token, "disconnect")
        finally:
            self.release(token)
        self.executor.shutdown(wait=True)
        self.closed = True
