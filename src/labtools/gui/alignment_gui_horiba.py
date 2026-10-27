"""Standalone HORIBA alignment display, with no laser or range controls."""
from __future__ import annotations
import asyncio
import sys
import traceback
from threading import Event
import numpy as np
from PyQt6.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from labtools.acquisition.alignment_spectrum import (
    AlignmentConfig, LatestSpectrum, detector_options, real_spectrometer, run_alignment)


class AlignmentThread(QThread):
    status = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config, mailbox, *, factory=real_spectrometer,
                 options_provider=detector_options, parent=None):
        super().__init__(parent)
        self.config = config
        self.mailbox = mailbox
        self.factory = factory
        self.options_provider = options_provider
        self.stop_event = Event()

    def run(self):
        try:
            asyncio.run(run_alignment(self.config, self.stop_event, self.mailbox.put,
                factory=self.factory, options_provider=self.options_provider,
                on_status=self.status.emit))
        except BaseException:
            self.failed.emit(traceback.format_exc())


class HoribaAlignmentWindow(QMainWindow):
    def __init__(self, *, factory=real_spectrometer, options_provider=detector_options):
        super().__init__()
        self._factory = factory
        self._options_provider = options_provider
        self._thread = None
        self._error = None
        self._close_pending = False
        self._mailbox = LatestSpectrum()
        self._latest = None
        self.setWindowTitle("HORIBA Spectrum Alignment")
        self.resize(1200, 760)
        self._apply_application_style()
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        title = QLabel("HORIBA Spectrum Alignment")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        row = QHBoxLayout()
        root.addLayout(row, 1)
        controls = QVBoxLayout()
        row.addLayout(controls)
        self.setup_group = QGroupBox("Acquisition setup")
        self.setup_group.setMaximumWidth(340)
        form = QFormLayout(self.setup_group)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(["syncerity", "symphony"])
        self.centre_box = self._number(0, 2200, 690, 3, " nm")
        self.exposure_box = self._number(.02, 1000, .1, 3, " s")
        self.dark_checkbox = QCheckBox()
        self.dark_checkbox.setAccessibleName("Dark subtraction")
        self.dark_checkbox.setToolTip("Closed-shutter dark, then open-shutter signal, at the same exposure. Slower than signal only.")
        self.gain_combo = QComboBox()
        self.speed_combo = QComboBox()
        for label, widget in [("Detector preset", self.preset_combo), ("Centre wavelength", self.centre_box),
                              ("Exposure", self.exposure_box), ("Dark subtraction", self.dark_checkbox),
                              ("Gain", self.gain_combo), ("Readout speed", self.speed_combo)]:
            form.addRow(label, widget)
        controls.addWidget(self.setup_group)
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setToolTip("Close other HORIBA applications. Presets may move the grating/exit mirror. 0.02 s shutter performance requires validation.")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setToolTip("Finishes the active operation, then disconnects. Physical shutter closure is not verified.")
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        self.autoscale = QCheckBox("Autoscale axes")
        self.autoscale.setChecked(True)
        controls.addWidget(self.autoscale)
        controls.addStretch(1)
        plot_panel = QFrame()
        plot_panel.setObjectName("plotPanel")
        plot = QVBoxLayout(plot_panel)
        plot.setContentsMargins(14, 12, 14, 12)
        row.addWidget(plot_panel, 1)
        self.figure = Figure(figsize=(8, 5), tight_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_xlabel("Wavelength (nm)")
        self.axes.set_ylabel("Intensity (counts)")
        self.axes.set_title("No spectrum acquired")
        self.figure.set_facecolor("#ffffff")
        self.axes.set_facecolor("#fbfcfd")
        self.axes.grid(True, color="#d9e2ec", linewidth=.8, alpha=.8)
        self.line, = self.axes.plot([], [], linewidth=1.2, color="#0b6fa4")
        self.canvas = FigureCanvas(self.figure)
        plot.addWidget(NavigationToolbar(self.canvas, self))
        plot.addWidget(self.canvas, 1)
        self.metrics = QLabel("No spectrum acquired")
        plot.addWidget(self.metrics)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusText")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._draw_latest)
        self.start_button.clicked.connect(self.start_alignment)
        self.stop_button.clicked.connect(self.stop_alignment)
        self.preset_combo.currentTextChanged.connect(self._update_preset)
        self._update_preset()

    def _apply_application_style(self) -> None:
        """Apply a restrained laboratory-instrument visual style."""
        self.setStyleSheet(
            """
            QMainWindow { background: #f3f5f7; }
            QWidget { color: #17212b; font-size: 13px; }
            QLabel#pageTitle { font-size: 25px; font-weight: 700; color: #102a43; }
            QLabel#pageSubtitle { color: #627d98; font-size: 13px; }
            QLabel#sectionTitle { font-size: 17px; font-weight: 700; color: #102a43; }
            QLabel#plotMeta { color: #627d98; }
            QLabel#hintText { color: #627d98; font-size: 12px; }
            QLabel#statusText { color: #334e68; padding: 4px 8px; }
            QFrame#plotPanel, QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 8px;
            }
            QGroupBox {
                margin-top: 13px;
                padding: 14px 10px 10px 10px;
                font-weight: 650;
                color: #243b53;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                min-height: 31px;
                padding: 2px 7px;
                background: #ffffff;
                border: 1px solid #bcccdc;
                border-radius: 5px;
                selection-background-color: #2680c2;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #2680c2;
            }
            QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
            QDoubleSpinBox:disabled { background: #f0f4f8; color: #829ab1; }
            QPushButton {
                min-height: 32px;
                padding: 4px 11px;
                background: #ffffff;
                border: 1px solid #9fb3c8;
                border-radius: 5px;
                color: #243b53;
            }
            QPushButton:hover { background: #f0f4f8; border-color: #627d98; }
            QPushButton:pressed { background: #d9e2ec; }
            QPushButton:disabled { background: #f0f4f8; color: #9fb3c8; border-color: #d9e2ec; }
            QPushButton#primaryButton {
                min-height: 39px;
                background: #0b6fa4;
                border: 1px solid #0b6fa4;
                color: white;
                font-weight: 700;
            }
            QPushButton#primaryButton:hover { background: #095d8a; }
            QPushButton#dangerButton { color: #b42318; border-color: #f0b4ae; }
            QCheckBox { spacing: 7px; }
            QScrollArea { background: transparent; }
            QSplitter::handle { background: transparent; }
            QStatusBar { background: #ffffff; border-top: 1px solid #d9e2ec; }
            """
        )


    @staticmethod
    def _number(lower, upper, value, decimals, suffix):
        box = QDoubleSpinBox()
        box.setDecimals(decimals)
        box.setRange(lower, upper)
        box.setValue(value)
        box.setSuffix(suffix)
        return box

    def _update_preset(self):
        options = self._options_provider(self.preset_combo.currentText())
        for combo, field, default in [(self.gain_combo, "gains", "default_gain"),
                                      (self.speed_combo, "speeds", "default_speed")]:
            combo.clear()
            for label, token in options[field]: combo.addItem(label, token)
            combo.setCurrentIndex(max(0, combo.findData(options[default])))
        self.exposure_box.setMinimum(0.02)

    def _config(self):
        return AlignmentConfig(self.preset_combo.currentText(), self.centre_box.value(),
            self.exposure_box.value(), self.dark_checkbox.isChecked(),
            int(self.gain_combo.currentData()), int(self.speed_combo.currentData()))

    def start_alignment(self):
        if self._thread is not None: return
        try:
            config = self._config()
            config.validate_detector(self._options_provider(config.preset))
        except Exception as exc:
            QMessageBox.warning(self, "Invalid alignment settings", str(exc))
            return
        self._error = None
        self._close_pending = False
        self._latest = None
        self._mailbox.take()
        self.line.set_data([], [])
        self.axes.set_title("Connecting...")
        self.canvas.draw_idle()
        self.metrics.setText("No spectrum acquired in this session")
        thread = AlignmentThread(config, self._mailbox, factory=self._factory,
                                 options_provider=self._options_provider, parent=self)
        self._thread = thread
        thread.status.connect(self._status)
        thread.failed.connect(self._failed)
        thread.finished.connect(self._finished)
        self.setup_group.setEnabled(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Starting...")
        self.timer.start()
        thread.start()

    @pyqtSlot(str)
    def _status(self, text):
        if self._thread is not None and self._thread.stop_event.is_set():
            self.status_label.setText("Stopping...")
        else:
            self.status_label.setText(text)

    def stop_alignment(self):
        if self._thread is None: return
        self._thread.stop_event.set()
        self.stop_button.setEnabled(False)
        self.status_label.setText("Stopping...")

    @pyqtSlot(str)
    def _failed(self, details):
        self._error = details
        self.status_label.setText("Alignment failed; completing cleanup...")

    @pyqtSlot()
    def _draw_latest(self):
        frame = self._mailbox.take()
        if frame is None: return
        first_frame = self._latest is None
        first_frame = self._latest is None
        self._latest = frame
        self.line.set_data(frame.wavelength_nm, frame.intensity)
        if self.autoscale.isChecked() or first_frame:
            self.axes.set_autoscalex_on(True)
            self.axes.set_autoscaley_on(True)
            self.axes.relim()
            self.axes.autoscale_view()
        self.axes.set_ylabel("Intensity (dark-subtracted counts)" if self.dark_checkbox.isChecked() else "Intensity (counts)")
        self.axes.set_title(f"{self.preset_combo.currentText().title()} | centre {frame.actual_centre_nm:.3f} nm")
        self.metrics.setText(f"Frame {frame.sequence} | peak {np.max(frame.intensity):.6g} counts | "
                             f"sum {np.sum(frame.intensity):.6g} counts | acquisition {frame.acquisition_s:.3f} s")
        self.canvas.draw_idle()

    @pyqtSlot()
    def _finished(self):
        self._draw_latest()
        self.timer.stop()
        thread, self._thread = self._thread, None
        if thread is not None: thread.deleteLater()
        self.setup_group.setEnabled(True)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if self._error:
            self.status_label.setText("Alignment failed. See error details.")
            box = QMessageBox(self)
            box.setWindowTitle("Alignment failed")
            box.setIcon(QMessageBox.Icon.Critical)
            box.setText(self._error.strip().splitlines()[-1])
            box.setDetailedText(self._error)
            box.exec()
        else:
            self.status_label.setText("Stopped")
        if self._close_pending:
            self.close()

    def closeEvent(self, event):
        if self._thread is not None:
            self._close_pending = True
            self.stop_alignment()
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = HoribaAlignmentWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
