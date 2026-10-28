"""Minimal shared manual-mirror/intensity-map composition; no eager native imports."""

from __future__ import annotations

from functools import partial
from threading import RLock

from labtools.acquisition.intensity_map import acquire_intensity_map
from labtools.runtime.labjack_service import LabJackWiring, create_labjack_session
from labtools.runtime.session import ResourceBusyError
from labtools.runtime.shared_map import SharedMapProvider


class ManualMirrorService:
    """A narrow application-owned manual lease; calls run on the session worker."""

    def __init__(self, session, *, owner="manual-mirror"):
        self._session = session
        self._owner = owner
        self._lease = None
        self._lock = RLock()

    @property
    def connected(self):
        with self._lock:
            return self._lease is not None

    def connect(self):
        """Reserve the mirror without connecting hardware or moving it."""
        with self._lock:
            if self._lease is not None:
                raise RuntimeError("Manual mirror is already connected")
            self._lease = self._session.reserve(self._owner, ("mirror",))

    def move(self, x_voltage, y_voltage):
        with self._lock:
            lease = self._lease
        if lease is None:
            raise RuntimeError("Manual mirror is not connected")
        lease.call("mirror", "move", x_voltage, y_voltage)

    def disconnect(self):
        """Release only the manual lease; never home or close application hardware."""
        with self._lock:
            lease, self._lease = self._lease, None
        if lease is not None:
            lease.release()

    def close(self):
        self.disconnect()

    def status(self):
        return self._session.status()


class SharedMirrorMapApplication:
    """Own one session and compose the two migrated tools around it."""

    def __init__(
        self,
        *,
        wiring=None,
        service_factory=None,
        backend="real",
        counter_provider=None,
    ):
        if backend != "real":
            raise ValueError(
                "Phase 2 shared composition supports real LabJack mode only"
            )
        wiring = LabJackWiring() if wiring is None else wiring
        self.session = create_labjack_session(wiring, service_factory=service_factory)
        self.manual_mirror = ManualMirrorService(self.session)
        self.map_provider = SharedMapProvider(
            self.session,
            wiring=wiring,
            backend=backend,
            counter_provider=counter_provider,
        )
        self.map_acquisition = partial(
            acquire_intensity_map, device_provider=self.map_provider
        )

    def create_mirror_window(self):
        from labtools.gui.mirror_voltage_gui import MirrorWindow

        return MirrorWindow(manual_service=self.manual_mirror)

    def create_map_window(self):
        from labtools.gui.intensity_map_gui import IntensityMapWindow

        return IntensityMapWindow(
            acquisition=self.map_acquisition,
            shared_mode=True,
        )

    def status(self):
        return self.session.status()

    def close(self):
        if self.manual_mirror.connected:
            raise ResourceBusyError(
                "Close the manual mirror tool before application shutdown"
            )
        self.session.close()
