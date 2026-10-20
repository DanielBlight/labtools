"""Lightweight mirror tester. Block the beam before use.

User-requested software limits: -10 to +10 V; DIO pin 2.
No instrument profile required. No movement on connect/disconnect/exit.
Commands are not measured voltage readbacks. Native driver calls can block.
"""
from __future__ import annotations

import math
import queue
import sys

from PyQt6.QtCore import QSettings, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

MIN_V = -10.0
MAX_V = 10.0
DIO_PIN = 2


def validate_target(x, y):
    if not all(math.isfinite(v) and MIN_V <= v <= MAX_V for v in (x, y)):
        raise ValueError("Target must be between -10 and +10 V")


class HardwareThread(QThread):
    done = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
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
                    from labtools.devices.labjack_u6 import LabJackU6
                    from labtools.devices.scanning_mirror import ScanningMirror
                    device = LabJackU6()
                    mirror = ScanningMirror(device, dio_pin=DIO_PIN)
                elif action == "disconnect":
                    if device is not None:
                        device.close()
                        device = None
                    mirror = None
                elif action == "move":
                    if mirror is None:
                        raise RuntimeError("Not connected")
                    validate_target(*target)
                    mirror.move(*target)
                self.done.emit(action, target)
        except Exception as exc:
            self.failed.emit(f"{exc}. Outputs unknown; a partial write is possible.")
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception as exc:
                    self.failed.emit(f"Close failed: {exc}")


class MirrorWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Labtools | Mirror")
        self.resize(410, 245)
        self.connected = False
        self.busy = False
        self.closing = False
        self.fault = False
        self.settings = QSettings("labtools", "ManualMirrorVoltages")
        self.worker = HardwareThread(self)
        self.worker.done.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        title = QLabel("Mirror voltages")
        title.setObjectName("title")
        layout.addWidget(title)
        panel = QFrame()
        panel.setObjectName("panel")
        form = QFormLayout(panel)
        self.x = self.spinbox("x")
        self.y = self.spinbox("y")
        form.addRow("X voltage", self.x)
        form.addRow("Y voltage", self.y)
        layout.addWidget(panel)
        row = QHBoxLayout()
        self.connection = QPushButton("Connect")
        self.move = QPushButton("Move X/Y")
        self.move.setObjectName("primary")
        self.zero = QPushButton("Zero X/Y")
        self.connection.clicked.connect(self.toggle_connection)
        self.move.clicked.connect(self.move_target)
        self.zero.clicked.connect(lambda: self.move_target(zero=True))
        for button in (self.connection, self.move, self.zero):
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QLabel("Disconnected | -10 to +10 V | DIO 2")
        self.status.setWordWrap(True)
        self.status.setObjectName("status")
        self.status.setToolTip("Commanded values only. No shutter control or automatic homing.")
        layout.addWidget(self.status)
        self.setStyleSheet("""
            QWidget { background: #f5f7fa; color: #102a43; }
            QLabel#title { font-size: 18px; font-weight: 600; }
            QLabel#status { color: #627d98; }
            QFrame#panel { background: white; border: 1px solid #d7e1ea;
                border-radius: 9px; }
            QFrame#panel QLabel { background: white; }
            QDoubleSpinBox { background: white; border: 1px solid #b8c7d4;
                border-radius: 5px; min-height: 28px; padding: 0px; }
            QPushButton { background: white; border: 1px solid #9fb5c8;
                border-radius: 5px; padding: 7px 10px; }
            QPushButton:hover { background: #e7f1f8; }
            QPushButton#primary { background: #147eaf; color: white; font-weight: 600; }
            QPushButton:disabled { color: #9aaab8; background: #e8edf2; }
        """)
        self.worker.start()
        self.refresh()

    def spinbox(self, key):
        box = QDoubleSpinBox()
        box.setRange(MIN_V, MAX_V)
        box.setDecimals(4)
        box.setSingleStep(0.01)
        box.setSuffix(" V")
        box.setKeyboardTracking(False)
        try:
            value = float(self.settings.value(key, 0.0))
            if math.isfinite(value) and MIN_V <= value <= MAX_V:
                box.setValue(value)
        except (ValueError, TypeError):
            pass
        return box

    def refresh(self):
        available = not (self.busy or self.closing or self.fault)
        self.connection.setText("Disconnect" if self.connected else "Connect")
        self.connection.setEnabled(available)
        self.move.setEnabled(available and self.connected)
        self.zero.setEnabled(available and self.connected)
        self.x.setEnabled(available)
        self.y.setEnabled(available)

    def submit(self, action, target=None):
        if self.busy or self.closing or self.fault or not self.worker.isRunning():
            return
        self.busy = True
        self.status.setText(f"{action.capitalize()}...")
        self.worker.commands.put_nowait((action, target))
        self.refresh()

    def toggle_connection(self):
        self.submit("disconnect" if self.connected else "connect")

    def move_target(self, checked=False, *, zero=False):
        if not self.connected:
            return
        self.x.interpretText()
        self.y.interpretText()
        target = (0.0, 0.0) if zero else (self.x.value(), self.y.value())
        validate_target(*target)
        self.submit("move", target)

    def completed(self, action, target):
        self.busy = False
        if action == "connect":
            self.connected = True
            self.status.setText("Connected | No move sent")
        elif action == "disconnect":
            self.connected = False
            self.status.setText("Disconnected | No home command sent")
        elif action == "move":
            self.status.setText(f"Commanded: X {target[0]:.4f} V | Y {target[1]:.4f} V")
        self.refresh()

    def failed(self, message):
        self.fault = True
        self.connected = False
        self.status.setText(message)
        self.refresh()
        QMessageBox.critical(self, "Mirror error", message)

    def finished(self):
        self.busy = False
        self.connected = False
        if self.closing:
            self.close()
        else:
            self.fault = True
            self.refresh()

    def closeEvent(self, event):
        if self.worker.isRunning():
            if self.busy and not self.closing:
                self.status.setText("Operation in progress; wait before closing.")
            elif not self.closing:
                self.closing = True
                self.worker.commands.put_nowait(("quit", None))
                self.status.setText("Disconnecting...")
                self.refresh()
            event.ignore()
            return
        self.settings.setValue("x", self.x.value())
        self.settings.setValue("y", self.y.value())
        self.settings.sync()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    window = MirrorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
