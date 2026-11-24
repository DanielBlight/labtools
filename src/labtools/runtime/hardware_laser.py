"""One lazy worker-owned ITC4000 connection with explicit output commands."""

import math
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from labtools.runtime.session import ResourceBusyError

# Existing working-lab policy from intensity_map_gui; no simulation 80 mA default.
MIN_CURRENT_A = 0.0
MAX_CURRENT_A = 0.040
THRESHOLD_CURRENT_A = 0.040
ADDRESS = "USB0::0x1313::0x804A::M00739898::INSTR"


def native_laser_factory():
    from labtools.devices.itc4000 import ITC4000

    return ITC4000(address=ADDRESS, threshold_current=THRESHOLD_CURRENT_A, max_current=MAX_CURRENT_A)


class HardwareLaser:
    """All VISA access stays on one thread. Connect never enables output."""

    simulated = False

    def __init__(self, workspace, *, factory=None):
        self.workspace = workspace
        self.factory = factory or native_laser_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labtools-laser")
        self._device = None
        self._lease = None
        self._lock = RLock()
        self._pending = 0
        self._closed = False
        self.connected = False
        self.output = None
        self.current_a = THRESHOLD_CURRENT_A
        self.identity = "Not probed"
        self.error = None
        self.command_error = None

    @property
    def busy(self):
        with self._lock:
            return self._pending > 0

    @property
    def status(self):
        with self._lock:
            if self.error:
                return "Laser: error/unknown - " + self.error
            if not self.connected:
                return "Laser: disconnected (real)"
            return "Laser: " + ("ON" if self.output is True else "OFF" if self.output is False else "unknown") + " (real)"

    def submit(self, command, current=None):
        if command not in {"connect", "apply", "on", "off", "disconnect"}:
            raise ValueError("Unknown laser command")
        if command in {"apply", "on"} and (isinstance(current, bool) or current is None or not math.isfinite(float(current)) or not MIN_CURRENT_A <= float(current) <= MAX_CURRENT_A):
            raise ValueError("Laser current must be finite and between 0.000 and 0.040 A inclusive")
        with self._lock:
            if self._closed:
                raise RuntimeError("Laser service is closed")
            self._pending += 1
        try:
            return self._executor.submit(self._run, command, current)
        except BaseException:
            with self._lock:
                self._pending -= 1
            raise

    def _run(self, command, current):
        optical = None
        try:
            # OFF/disconnect remain possible after source invalidation or a fault.
            if command not in {"off", "disconnect"}:
                self.workspace._require_open()
            if command in {"apply", "on"}:
                self.workspace.hardware_ready()
                if self.error:
                    raise RuntimeError("Laser faulted; switch output off and disconnect before reconnecting")
                optical = self.workspace._ownership.reserve("Spectrum")
            if command == "connect":
                if self._device is None:
                    self._lease = self.workspace._ownership.reserve("Laser")
                    try:
                        self._device = self.factory()
                        self.identity = self._device.identify()
                        self.output = self._device.get_diode_output()
                        self.current_a = self._device.get_current()
                        self.connected = True
                        self.error = None
                    except BaseException as primary:
                        if self._device is not None:
                            try:
                                self._device.close()
                            except BaseException as cleanup:
                                # Retain handle/lease for an explicit OFF/disconnect retry.
                                self.connected = True
                                primary.add_note(f"Laser startup cleanup failed: {cleanup!r}")
                                raise primary from cleanup
                            self._device = None
                        self.connected = False
                        if self._lease is not None:
                            self._lease.release()
                            self._lease = None
                        raise
            elif command == "disconnect":
                if self._device is not None:
                    # Wrapper close preserves its output-off and cleanup contract.
                    self._device.close()
                    self._device = None
                    self.connected = False
                    self.output = None
                    self.error = None
                    if self._lease is not None:
                        self._lease.release()
                        self._lease = None
            elif command == "off" and self._device is None:
                return self.status
            else:
                if self._device is None:
                    raise RuntimeError("Connect the laser controller first")
                if command in {"apply", "on"}:
                    self._device.set_current(float(current))
                if command == "on":
                    self._device.enable_diode()
                elif command == "off":
                    self._device.disable_diode()
                self.output = self._device.get_diode_output()
                self.current_a = self._device.get_current()
                if command == "off":
                    self.error = None
            self.command_error = None
            return self.status
        except ResourceBusyError as error:
            self.command_error = str(error)
            raise
        except Exception as error:
            self.output = None
            self.error = f"{type(error).__name__}: {error}"
            raise
        finally:
            if optical is not None:
                optical.release()
            with self._lock:
                self._pending -= 1

    def close(self):
        if self.busy or self._device is not None:
            raise RuntimeError("Disconnect the laser and wait for cleanup before closing its service")
        if not self._closed:
            self._executor.shutdown(wait=True)
            self._closed = True
