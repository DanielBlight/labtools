"""Read-only native workspace window. Never loads simulation panels or devices."""

from __future__ import annotations

import json
import sys


def create_window(workspace):
    # Qt and operator panels remain lazy: headless launch never loads them.
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    from labtools.gui.native_workflow_panels import NativeMapPanel, NativeSpectrumPanel
    from labtools.simulation.workspace import (
        busy_workflows,
        close_workflows,
        stop_workflows,
    )

    class NativeWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Labtools native workspace - execution disabled")
            self.resize(1500, 1000)
            self.pages = {}
            body = QWidget()
            layout = QVBoxLayout(body)
            label = QLabel(
                "NATIVE CANDIDATE: operator drafts only. No hardware is opened. "
                "Settings and detector serials are source expectations, not readbacks."
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs)
            overview = QWidget()
            overview_layout = QVBoxLayout(overview)
            self.report = QPlainTextEdit()
            self.report.setReadOnly(True)
            overview_layout.addWidget(self.report)
            self.refresh_button = QPushButton("Refresh source status (no device probe)")
            self.refresh_button.clicked.connect(self.refresh)
            overview_layout.addWidget(self.refresh_button)
            self.preview_button = QPushButton("Validate and preview operator drafts (no execution)")
            self.preview_button.clicked.connect(self.preview)
            overview_layout.addWidget(self.preview_button)
            self.tabs.addTab(overview, "Configuration and draft preview")
            try:
                self.pages["Intensity map"] = NativeMapPanel(workspace=workspace)
                self.pages["Spectrum"] = NativeSpectrumPanel(workspace=workspace)
                for name, page in self.pages.items():
                    page.setParent(self.tabs)
                    page.setWindowFlags(Qt.WindowType.Widget)
                    self.tabs.addTab(page, name)
            except BaseException:
                for page in self.pages.values():
                    page.close()
                raise
            mapping, spectrum = self.pages["Intensity map"], self.pages["Spectrum"]
            self.operation_buttons = [
                mapping.start_button, mapping.resume_button,
                spectrum.connect_button, spectrum.acquire_button, spectrum.capture_dark_button,
            ]
            close_button = QPushButton("Close workspace")
            close_button.clicked.connect(self.close)
            layout.addWidget(close_button)
            self.setCentralWidget(body)
            self.refresh()

        def refresh(self):
            try:
                data = workspace.describe()
            except (OSError, ValueError, RuntimeError) as error:
                self.report.setPlainText(
                    "Source status invalid; close and relaunch after correcting inputs.\n" + str(error))
                for page in self.pages.values():
                    page.setEnabled(False)
            else:
                self.report.setPlainText(json.dumps(data, indent=2))

        def preview(self):
            try:
                data = workspace.workflow_preview(
                    self.pages["Intensity map"]._config(),
                    self.pages["Spectrum"]._snapshot_settings(),
                )
                spectrum = self.pages["Spectrum"]
                mode = spectrum._selected_dark_mode()
                dark = spectrum.pre_taken_dark
                if mode == "pre_taken":
                    if dark is None:
                        raise ValueError("Load a compatible native dark archive before previewing pre-taken subtraction")
                    dark.validate_for(spectrum._snapshot_settings())
                data["dark_mode"] = mode
                data["dark_record_id"] = dark.record_id if mode == "pre_taken" else None
                self.report.setPlainText(json.dumps(
                    {"source_status": workspace.describe(), "operator_draft": data}, indent=2,
                ))
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.report.setPlainText("Draft invalid; execution remains disabled.\n" + str(error))
            self.tabs.setCurrentIndex(0)

        def closeEvent(self, event):
            if busy_workflows(self.pages):
                stop_workflows(self.pages)
                self.report.setPlainText("Stop requested; wait for worker cleanup and close again.")
                event.ignore()
                return
            if not close_workflows(self.pages):
                event.ignore()
                return
            workspace.close()
            super().closeEvent(event)

    return NativeWindow()


def launch_window(workspace):
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        raise RuntimeError("Launch native workspace in its own process, not an existing Qt event loop")
    app = QApplication([sys.argv[0]])
    window = create_window(workspace)
    app.aboutToQuit.connect(workspace.close)
    window.show()
    return app.exec()
