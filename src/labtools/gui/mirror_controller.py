"""Persistent manual-mirror command worker with an injectable backend."""

import queue

from PyQt6.QtCore import QThread, pyqtSignal

from labtools.runtime.mirror_backend import open_real_mirror, validate_target


class HardwareThread(QThread):
    done = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None, *, backend_factory=None, manual_service=None):
        super().__init__(parent)
        self.backend_factory = backend_factory or open_real_mirror
        self.manual_service = manual_service
        self.commands = queue.Queue(maxsize=1)

    def run(self):
        device = None
        mirror = None
        try:
            while True:
                action, target = self.commands.get()
                if action == "quit":
                    return
                if action == "connect":
                    if self.manual_service is not None:
                        self.manual_service.connect()
                    else:
                        if device is not None:
                            raise RuntimeError("Already connected")
                        device, mirror = self.backend_factory()
                elif action == "disconnect":
                    if self.manual_service is not None:
                        self.manual_service.disconnect()
                    else:
                        if device is not None:
                            device.close()
                            device = None
                        mirror = None
                elif action == "move":
                    validate_target(*target)
                    if self.manual_service is not None:
                        self.manual_service.move(*target)
                    else:
                        if mirror is None:
                            raise RuntimeError("Not connected")
                        mirror.move(*target)
                self.done.emit(action, target)
        except Exception as exc:  # noqa: BLE001 - report worker failures via Qt
            self.failed.emit(f"{exc}. Outputs unknown; a partial write is possible.")
        finally:
            if self.manual_service is not None:
                try:
                    self.manual_service.disconnect()
                except Exception as exc:  # noqa: BLE001 - report release failures via Qt
                    self.failed.emit(f"Release failed: {exc}")
            if device is not None:
                try:
                    device.close()
                except Exception as exc:  # noqa: BLE001 - report device close failures via Qt
                    self.failed.emit(f"Close failed: {exc}")
