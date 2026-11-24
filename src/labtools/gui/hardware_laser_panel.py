"""Asynchronous real laser controls; connection and output activation are separate."""

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDoubleSpinBox, QLabel, QPushButton, QVBoxLayout, QWidget

from labtools.gui.workspace_studio import add_card, scroll_content
from labtools.runtime.hardware_laser import (
    ADDRESS,
    MAX_CURRENT_A,
    MIN_CURRENT_A,
    THRESHOLD_CURRENT_A,
)


class HardwareLaserPanel(QWidget):
    def __init__(self, workspace, indicator, parent=None):
        super().__init__(parent)
        self.model = workspace.laser
        self.indicator = indicator
        self._futures = []
        self._shutdown_requested = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        title = QLabel("Laser")
        title.setObjectName("studioTitle")
        layout.addWidget(title)
        scroll, content = scroll_content()
        layout.addWidget(scroll, 1)
        self.current = QDoubleSpinBox()
        self.current.setDecimals(3)
        self.current.setRange(MIN_CURRENT_A, MAX_CURRENT_A)
        self.current.setSingleStep(0.001)
        self.current.setSuffix(" A")
        self.current.setValue(THRESHOLD_CURRENT_A)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.note = QLabel("Real ITC4000. Connect reads state only; Output ON is separate. Working-lab limit: 0.040 A.\n" + ADDRESS)
        self.note.setWordWrap(True)
        self.connect_button = QPushButton("Connect")
        self.apply_button = QPushButton("Apply current")
        self.on_button = QPushButton("Output ON")
        self.off_button = QPushButton("Output OFF")
        self.disconnect_button = QPushButton("Disconnect")
        card = add_card(content, "Laser controller", [(None, self.note), ("Current", self.current),
                        (None, self.connect_button), (None, self.apply_button), (None, self.on_button),
                        (None, self.off_button), (None, self.disconnect_button), (None, self.state)])
        card.setMaximumWidth(700)
        content.addStretch(1)
        for button, command in ((self.connect_button, "connect"), (self.apply_button, "apply"),
                                (self.on_button, "on"), (self.off_button, "off"), (self.disconnect_button, "disconnect")):
            button.clicked.connect(lambda checked=False, cmd=command: self.command(cmd))
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self.update_state()

    @property
    def busy(self):
        return self.model.busy or bool(self._futures)

    def command(self, command):
        try:
            if command == "connect":
                self._shutdown_requested = False
            future = self.model.submit(command, self.current.value())
            self._futures.append(future)
        except (ValueError, RuntimeError) as error:
            self.state.setText(str(error))
        self.update_state()

    def request_shutdown(self):
        if not self._shutdown_requested and (self.model.connected or self.busy):
            self._shutdown_requested = True
            self.command("disconnect")

    def _poll(self):
        pending = []
        for future in self._futures:
            if future.done():
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - service preserves error/unknown state
                    self.state.setText("Laser command failed: " + str(error))
            else:
                pending.append(future)
        self._futures = pending
        self.update_state()

    def update_state(self):
        busy = self.busy
        connected = self.model.connected
        self.state.setText(self.model.status + "\n" + self.model.identity + ("\nCommand refused: " + self.model.command_error if self.model.command_error else ""))
        self.indicator.setText(self.model.status)
        self.connect_button.setEnabled(not busy and not connected)
        self.apply_button.setEnabled(not busy and connected and not self.model.error)
        self.on_button.setEnabled(not busy and connected and not self.model.error)
        self.off_button.setEnabled(connected or busy)
        self.disconnect_button.setEnabled(not busy and connected)
        self.current.setEnabled(not busy)

    def closeEvent(self, event):
        if self.busy or self.model.connected:
            self.request_shutdown()
            event.ignore()
            return
        self.timer.stop()
        super().closeEvent(event)
