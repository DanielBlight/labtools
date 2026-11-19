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

    from labtools.gui.camera_window import CameraWindow
    from labtools.gui.native_anneal_panel import NativeAnnealPanel
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
            self.camera_window = CameraWindow(self, reserve=workspace.reserve_camera)
            body = QWidget()
            layout = QVBoxLayout(body)
            label = QLabel(
                "NATIVE CANDIDATE: operator drafts only. No hardware is opened. "
                "Settings and detector serials are source expectations, not readbacks."
            )
            label.setWordWrap(True)
            layout.addWidget(label)
            self.camera_button = QPushButton("Open camera window")
            self.camera_button.clicked.connect(self.open_camera)
            layout.addWidget(self.camera_button)
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
            self.save_button = QPushButton("Save operator settings")
            self.save_button.clicked.connect(self.save_preferences)
            overview_layout.addWidget(self.save_button)
            self.stop_all_button = QPushButton("Stop all workflows")
            self.stop_all_button.clicked.connect(self.stop_all)
            overview_layout.addWidget(self.stop_all_button)
            self.tabs.addTab(overview, "Configuration and draft preview")
            try:
                self.pages["Intensity map"] = NativeMapPanel(workspace=workspace)
                self.pages["Spectrum"] = NativeSpectrumPanel(workspace=workspace)
                self.pages["Annealing"] = NativeAnnealPanel(workspace=workspace, camera_window=self.camera_window)
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
                self.pages["Annealing"].start_button,
            ]
            close_button = QPushButton("Close workspace")
            close_button.clicked.connect(self.close)
            layout.addWidget(close_button)
            self.setCentralWidget(body)
            self.restore_display()
            self.refresh()

        def open_camera(self):
            self.camera_window.show()
            self.camera_window.raise_()
            self.camera_window.activateWindow()

        def restore_display(self):
            data = workspace.drafts.display
            mapping, spectrum, anneal = (self.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
            for key, widget in (("map_log", mapping.log_colour_scale), ("map_manual_limits", mapping.custom_colour_limits),
                                ("spectrum_csv", spectrum.save_csv), ("spectrum_png", spectrum.save_png)):
                if key in data:
                    widget.setChecked(data[key])
            for key, widget in (("map_min", mapping.colour_min), ("map_max", mapping.colour_max),
                                ("camera_exposure_ms", anneal.camera_exposure_ms), ("camera_gain", anneal.camera_gain),
                                ("camera_interval_ms", anneal.camera_interval_ms), ("camera_white_level", self.camera_window.white_level)):
                if key in data:
                    widget.setValue(data[key])
            if "spectrum_output" in data:
                spectrum.output_directory.setText(data["spectrum_output"])

        def display_preferences(self):
            mapping, spectrum, anneal = (self.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
            return {"map_log": mapping.log_colour_scale.isChecked(),
                    "map_manual_limits": mapping.custom_colour_limits.isChecked(),
                    "map_min": mapping.colour_min.value(), "map_max": mapping.colour_max.value(),
                    "spectrum_output": spectrum.output_directory.text(), "spectrum_csv": spectrum.save_csv.isChecked(),
                    "spectrum_png": spectrum.save_png.isChecked(), "camera_exposure_ms": anneal.camera_exposure_ms.value(),
                    "camera_gain": anneal.camera_gain.value(), "camera_interval_ms": anneal.camera_interval_ms.value(),
                    "camera_white_level": self.camera_window.white_level.value()}

        def save_preferences(self):
            drafts = {"display": self.display_preferences()}
            for name, key, method in (("Intensity map", "map", "_config"), ("Spectrum", "spectrum", "_snapshot_settings"),
                                      ("Annealing", "anneal", "_build_config")):
                try:
                    drafts[key] = getattr(self.pages[name], method)()
                except (OSError, ValueError, TypeError) as error:
                    workspace.drafts.store.messages.append(f"{name} draft not saved: {error}")
            try:
                workspace.save_preferences(**drafts)
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.report.setPlainText("Settings could not be saved: " + str(error))
                return False
            self.report.setPlainText("Operator settings saved to " + str(workspace.drafts.store.path)
                                     + "\n" + "\n".join(workspace.drafts.store.messages))
            return True

        def stop_all(self):
            errors = stop_workflows(self.pages)
            if self.camera_window.busy:
                self.camera_window.request_stop()
            if errors:
                self.report.setPlainText("Stop request errors:\n" + "\n".join(errors))

        def any_busy(self):
            return bool(busy_workflows(self.pages)) or self.camera_window.busy

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
                from dataclasses import asdict

                anneal = asdict(self.pages["Annealing"]._build_config())
                anneal["output_root"] = str(anneal["output_root"])
                data["anneal"] = anneal
                data["anneal_execution_enabled"] = False
                data["dark_mode"] = mode
                data["dark_record_id"] = dark.record_id if mode == "pre_taken" else None
                self.report.setPlainText(json.dumps(
                    {"source_status": workspace.describe(), "operator_draft": data}, indent=2,
                ))
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.report.setPlainText("Draft invalid; execution remains disabled.\n" + str(error))
            self.tabs.setCurrentIndex(0)

        def closeEvent(self, event):
            if self.any_busy():
                self.stop_all()
                self.report.setPlainText("Stop requested; wait for worker cleanup and close again.")
                event.ignore()
                return
            if not self.save_preferences():
                from PyQt6.QtWidgets import QMessageBox

                answer = QMessageBox.question(self, "Settings not saved", "Close without saving operator settings?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                              QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            if not self.camera_window.close():
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
