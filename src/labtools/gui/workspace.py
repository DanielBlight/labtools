"""One operator window composing existing simulation-only workflow panels.

This is not a shared native-device session. Standalone windows remain unchanged.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from labtools.gui.workspace_panels import OwnedMapPanel, OwnedSpectrumPanel
from labtools.simulation.ownership import WorkspaceOwnership
from labtools.simulation.workspace import (
    busy_workflows,
    close_workflows,
    stop_workflows,
)


class SimulationWorkspace(QMainWindow):
    """Reuse both complete workflows with one navigation and cooperative Stop all."""

    def __init__(self, *, output_root: Path):
        super().__init__()
        self.setWindowTitle("Labtools Workspace - SIMULATION ONLY")
        self.resize(1500, 1000)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        banner = QLabel(
            "SIMULATION ONLY | Spectrum and intensity mapping | No hardware is connected"
        )
        banner.setWordWrap(True)
        layout.addWidget(banner)
        self.output_root = Path(output_root).expanduser().resolve()
        output_label = QLabel(f"Outputs: {self.output_root} (separate Maps and Spectra folders)")
        output_label.setWordWrap(True)
        layout.addWidget(output_label)
        controls = QHBoxLayout()
        self.activity = QLabel("Ready")
        self.stop_all_button = QPushButton("Stop all active workflows")
        self.stop_all_button.clicked.connect(self.stop_all)
        controls.addWidget(self.activity, 1)
        controls.addWidget(self.stop_all_button)
        layout.addLayout(controls)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)
        self.pages = {}
        self.ownership = WorkspaceOwnership()
        try:
            mapping = OwnedMapPanel(ownership=self.ownership)
            self.pages["Intensity map"] = mapping
            mapping.output_root.setText(str(self.output_root / "Maps"))
            spectrum = OwnedSpectrumPanel(ownership=self.ownership)
            self.pages["Spectrum"] = spectrum
            spectrum.output_directory.setText(str(self.output_root / "Spectra"))
            spectrum.start_wl.setValue(500)
            spectrum.end_wl.setValue(600)
            spectrum.exposure_box.setValue(0.065)
            for name, page in self.pages.items():
                # Keep each existing window's controls, status bar and close lifecycle.
                page.setParent(self.tabs)
                page.setWindowFlags(Qt.WindowType.Widget)
                self.tabs.addTab(page, name)
        except BaseException:
            for page in self.pages.values():
                page.close()
            self.ownership.close()
            raise
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(200)
        self._activity_timer.timeout.connect(self.refresh_activity)
        self._activity_timer.start()
        self.refresh_activity()

    def refresh_activity(self):
        active = busy_workflows(self.pages)
        owners = [resource.owner for resource in self.ownership.status().resources if resource.owner]
        self.activity.setText(
            "Reserved by: " + ", ".join(owners) + " (includes cleanup)"
            if owners else "Active: " + ", ".join(active) if active else "Ready - all workers idle"
        )
        self.stop_all_button.setEnabled(bool(active))

    def stop_all(self):
        errors = stop_workflows(self.pages)
        if errors:
            self.activity.setText("Stop request errors: " + "; ".join(errors))
        else:
            self.activity.setText("Stop requested; wait for workflow cleanup before closing")

    def closeEvent(self, event):
        # Recheck synchronously; the timer is presentation only, not a close guard.
        if busy_workflows(self.pages):
            self.stop_all()
            event.ignore()
            return
        if not close_workflows(self.pages):
            self.activity.setText("A workflow declined close; inspect its status")
            event.ignore()
            return
        self.ownership.close()
        self._activity_timer.stop()
        super().closeEvent(event)
