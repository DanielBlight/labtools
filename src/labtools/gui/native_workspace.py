"""Source-backed workspace: disabled default, explicit simulation or real HORIBA."""

from __future__ import annotations

import json
import sys


def create_window(workspace):
    # Qt and operator panels remain lazy: headless launch never loads them.
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import (
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QSizePolicy,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    from labtools.gui.camera_tools import CameraWindow
    from labtools.gui.native_anneal_panel import NativeAnnealPanel
    from labtools.gui.native_workflow_panels import NativeMapPanel, NativeSpectrumPanel
    from labtools.gui.operator_ui import (
        STYLE,
        fit_initial_window,
        polish_panel,
        protect_parameter_wheels,
    )
    from labtools.simulation.workspace import (
        busy_workflows,
        close_workflows,
        stop_workflows,
    )

    simulated = bool(getattr(workspace, "simulation_only", False))
    hardware_spectrum = bool(getattr(workspace, "hardware_spectrum_enabled", False))
    all_hardware = bool(getattr(workspace, "all_hardware_enabled", False))
    runtime = None
    if simulated or hardware_spectrum:
        from labtools.runtime.operator_spectrum import ensure_operator_spectrum

        runtime = ensure_operator_spectrum(workspace)
    if simulated:
        from labtools.gui.simulated_workflow_panels import (
            SimulatedAnnealPanel,
            SimulatedMapPanel,
            SimulatedSpectrumPanel,
        )

    class NativeWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self._close_after_cleanup = False
            self._close_retry = QTimer(self)
            self._close_retry.setInterval(50)
            self._close_retry.timeout.connect(self._retry_close)
            self.setWindowTitle("Labtools Workspace - SIMULATION ONLY" if simulated
                                else "Labtools Workspace - real hardware" if all_hardware
                                else "Labtools Workspace - real HORIBA" if hardware_spectrum
                                else "Labtools native workspace - execution disabled")
            self.setStyleSheet(STYLE)
            fit_initial_window(self)
            self.pages = {}
            self.camera_window = CameraWindow(self, reserve=workspace.reserve_camera)
            if simulated:
                self.camera_window.source.removeItem(1)
                self.camera_window.source.setToolTip("Whole-workspace simulation: real camera selection is unavailable")
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(10)
            header = QHBoxLayout()
            app_title = QLabel("Labtools")
            app_title.setObjectName("appTitle")
            header.addWidget(app_title)
            header.addStretch(1)
            self.mode_badge = QLabel("Simulation" if simulated else "Real hardware" if all_hardware else "Real HORIBA" if hardware_spectrum else "Native execution disabled")
            self.mode_badge.setObjectName("modeBadge")
            header.addWidget(self.mode_badge)
            self.camera_button = QPushButton("Camera")
            self.camera_button.clicked.connect(self.open_camera)
            header.addWidget(self.camera_button)
            self.stop_all_button = QPushButton("Stop all")
            self.stop_all_button.clicked.connect(self.stop_all)
            header.addWidget(self.stop_all_button)
            layout.addLayout(header)
            self.tabs = QTabWidget()
            layout.addWidget(self.tabs, 1)
            overview = QWidget()
            overview_layout = QVBoxLayout(overview)
            title = QLabel("Workspace")
            title.setObjectName("pageTitle")
            overview_layout.addWidget(title)
            summary = QFormLayout()
            self.configuration_label = QLabel(str(workspace.plan.configuration_id))
            self.configuration_label.setWordWrap(True)
            self.configuration_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.configuration_label.setMinimumWidth(360)
            self.configuration_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            summary.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            summary.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            summary.addRow('Configuration', self.configuration_label)
            summary.addRow("Mode", QLabel("Simulation" if simulated else "All real hardware" if all_hardware else "Real HORIBA spectrum/alignment" if hardware_spectrum else "Native execution disabled"))
            self.overview_status = QLabel("Ready")
            self.overview_status.setWordWrap(True)
            summary.addRow("Status", self.overview_status)
            overview_layout.addLayout(summary)
            actions = QHBoxLayout()
            self.refresh_button = QPushButton("Refresh")
            self.refresh_button.clicked.connect(self.refresh)
            actions.addWidget(self.refresh_button)
            self.preview_button = QPushButton("Validate settings")
            self.preview_button.clicked.connect(self.preview)
            actions.addWidget(self.preview_button)
            self.save_button = QPushButton("Save settings")
            self.save_button.clicked.connect(self.save_preferences)
            actions.addWidget(self.save_button)
            actions.addStretch(1)
            overview_layout.addLayout(actions)
            self.details_toggle = QToolButton()
            self.details_toggle.setText("Diagnostics")
            self.details_toggle.setCheckable(True)
            self.details_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.details_toggle.setArrowType(Qt.ArrowType.RightArrow)
            overview_layout.addWidget(self.details_toggle)
            self.report = QPlainTextEdit()
            self.report.setReadOnly(True)
            self.report.setVisible(False)
            self.details_toggle.toggled.connect(self.report.setVisible)
            self.details_toggle.toggled.connect(lambda expanded: self.details_toggle.setArrowType(
                Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow))
            overview_layout.addWidget(self.report, 1)
            overview_layout.addStretch(1)
            self.tabs.addTab(overview, "Workspace")
            try:
                map_panel = SimulatedMapPanel if simulated else NativeMapPanel
                spectrum_panel = SimulatedSpectrumPanel if simulated else NativeSpectrumPanel
                if hardware_spectrum:
                    from labtools.gui.hardware_spectrum_panel import (
                        HardwareSpectrumPanel,
                    )

                    spectrum_panel = HardwareSpectrumPanel
                anneal_panel = SimulatedAnnealPanel if simulated else NativeAnnealPanel
                if all_hardware:
                    from labtools.gui.hardware_panels import (
                        HardwareAnnealPanel,
                        HardwareMapPanel,
                    )

                    map_panel, anneal_panel = HardwareMapPanel, HardwareAnnealPanel
                self.pages["Intensity map"] = map_panel(workspace=workspace)
                self.pages["Spectrum"] = spectrum_panel(workspace=workspace)
                self.pages["Annealing"] = anneal_panel(workspace=workspace, camera_window=self.camera_window)
                if runtime is not None:
                    from labtools.gui.workspace_alignment import WorkspaceAlignmentPanel

                    self.pages["Alignment"] = WorkspaceAlignmentPanel(workspace=workspace, runtime=runtime)
                for name, page in self.pages.items():
                    if name == "Alignment":
                        page.setParent(self, Qt.WindowType.Window)
                        page.hide()
                        continue
                    page.setParent(self.tabs)
                    page.setWindowFlags(Qt.WindowType.Widget)
                    if name != "Alignment":
                        polish_panel(page, simulated=simulated)
                    self.tabs.addTab(page, name)
                if "Alignment" in self.pages:
                    alignment = self.pages["Alignment"]
                    self.tabs.removeTab(self.tabs.indexOf(alignment))
                    alignment.setWindowTitle("Labtools Alignment")
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
            self.setCentralWidget(body)
            protect_parameter_wheels(self)
            self.camera_window.setStyleSheet(STYLE)
            self.restore_display()
            self.refresh()
            from labtools.gui.workspace_studio import install_studio
            install_studio(self, workspace)
            if "Alignment" in self.pages:
                protect_parameter_wheels(self.pages["Alignment"])
            from labtools.gui.workspace_hub import install_hub

            install_hub(self, workspace)
            if "Alignment" in self.pages:
                self.alignment_window = self.pages["Alignment"]
                self.alignment_window.setStyleSheet(self.styleSheet())
                fit_initial_window(self.alignment_window, preferred=(1050, 700))
                self.open_alignment_button = QPushButton("Open alignment")
                self.open_alignment_button.clicked.connect(self.open_alignment)
                self.pages["Spectrum"].centralWidget().layout().insertWidget(1, self.open_alignment_button)
            if simulated or all_hardware:
                from labtools.gui.experiment_panels import install_experiment_tabs

                install_experiment_tabs(self, workspace)
                from labtools.gui.workspace_mirror_popup import install_mirror_popup

                install_mirror_popup(self, workspace)
                from labtools.gui.sample_stage_popup import install_sample_stage

                install_sample_stage(self, workspace)
                protect_parameter_wheels(self.stage_window)
                protect_parameter_wheels(self)
                protect_parameter_wheels(self.mirror_window)
            from labtools.analysis.gui import AnalysisPanel

            self.analysis_panel = AnalysisPanel(self)
            protect_parameter_wheels(self)
            self.tabs.addTab(self.analysis_panel, "Analysis")
            if all_hardware:
                self.overview_status.setText("Ready - real hardware; connections and outputs require explicit actions")
            elif hardware_spectrum:
                self.overview_status.setText("Ready - real HORIBA. Map, Annealing and laser remain disabled.")

        def open_alignment(self):
            self.alignment_window.show()
            self.alignment_window.raise_()
            self.alignment_window.activateWindow()

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

            if "Sequences" in self.pages:
                from labtools.gui.experiment_panels import (
                    restore_experiment_preferences,
                )

                restore_experiment_preferences(self, data)
            if hasattr(mapping, "focus_controls"):
                mapping.focus_controls.restore(data)

        def display_preferences(self):
            mapping, spectrum, anneal = (self.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
            from labtools.gui.experiment_panels import experiment_preferences

            return {**experiment_preferences(self),
                    **(mapping.focus_controls.preferences() if hasattr(mapping, "focus_controls") else {}), "map_log": mapping.log_colour_scale.isChecked(),
                    "map_manual_limits": mapping.custom_colour_limits.isChecked(),
                    "map_min": mapping.colour_min.value(), "map_max": mapping.colour_max.value(),
                    "spectrum_output": spectrum.output_directory.text(), "spectrum_csv": spectrum.save_csv.isChecked(),
                    "spectrum_png": spectrum.save_png.isChecked(), "camera_exposure_ms": anneal.camera_exposure_ms.value(),
                    "camera_gain": anneal.camera_gain.value(), "camera_interval_ms": anneal.camera_interval_ms.value(),
                    "camera_white_level": self.camera_window.white_level.value()}

        def save_preferences(self):
            drafts = {"display": self.display_preferences()}
            if "Alignment" in self.pages:
                from labtools.gui.workspace_hub import alignment_draft
                from labtools.runtime.workspace_settings import ALIGNMENT_FIELDS

                try:
                    settings = alignment_draft(self)
                    drafts["alignment"] = {key: getattr(settings, key) for key in ALIGNMENT_FIELDS}
                except (ValueError, TypeError, KeyError) as error:
                    workspace.drafts.store.messages.append("Alignment settings not saved: " + str(error))
            for name, key, method in (("Intensity map", "map", "_config"), ("Spectrum", "spectrum", "_snapshot_settings"),
                                      ("Annealing", "anneal", "_build_config")):
                try:
                    drafts[key] = getattr(self.pages[name], method)()
                except (OSError, ValueError, TypeError) as error:
                    workspace.drafts.store.messages.append(f"{name} draft not saved: {error}")
            try:
                workspace.save_preferences(**drafts)
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.overview_status.setText("Settings could not be saved: " + str(error))
                self.report.setPlainText("Settings could not be saved: " + str(error))
                return False
            self.overview_status.setText("Settings saved")
            self.report.setPlainText("Operator settings saved to " + str(workspace.drafts.store.path)
                                     + "\n" + "\n".join(workspace.drafts.store.messages))
            return True

        def stop_all(self):
            errors = stop_workflows(self.pages)
            if all_hardware and (self.laser_panel.model.connected or self.laser_panel.busy):
                self.laser_panel.command("off")
            if self.camera_window.busy:
                self.camera_window.request_stop()
            if errors:
                self.overview_status.setText("Stop request errors: " + "; ".join(errors))
                self.details_toggle.setChecked(True)
                self.tabs.setCurrentIndex(0)
                self.report.setPlainText("Stop request errors:\n" + "\n".join(errors))

        def any_busy(self):
            hub = getattr(self, "workspace_hub", None)
            laser = getattr(self, "laser_panel", None)
            analysis = getattr(self, "analysis_panel", None)
            saving = any(getattr(button, "_save_job", None) is not None for button in self.findChildren(QPushButton))
            return (saving or (analysis is not None and analysis.future is not None)
                    or bool(busy_workflows(self.pages)) or self.camera_window.busy
                    or bool(hub is not None and hub.busy)
                    or bool(all_hardware and laser is not None and laser.busy))

        def refresh(self):
            try:
                data = workspace.describe()
            except (OSError, ValueError, RuntimeError) as error:
                self.overview_status.setText("Configuration invalid: " + str(error))
                self.details_toggle.setChecked(True)
                self.report.setPlainText(
                    "Source status invalid; close and relaunch after correcting inputs.\n" + str(error))
                for page in self.pages.values():
                    page.setEnabled(False)
            else:
                self.overview_status.setText("Ready" if simulated else "Ready - real hardware" if all_hardware else "Ready - real HORIBA; other native workflows disabled" if hardware_spectrum else "Native execution disabled")
                self.report.setPlainText(json.dumps(data, indent=2))

        def preview(self):
            self.details_toggle.setChecked(True)
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
                data["anneal_simulation_enabled"] = simulated
                data["dark_mode"] = mode
                data["dark_record_id"] = dark.record_id if mode == "pre_taken" else None
                self.report.setPlainText(json.dumps(
                    {"source_status": workspace.describe(), "operator_draft": data}, indent=2,
                ))
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.report.setPlainText("Draft invalid; no operation started.\n" + str(error))
            self.tabs.setCurrentIndex(0)

        def _retry_close(self):
            if self._close_after_cleanup and not self.any_busy():
                self._close_retry.stop()
                self.close()

        def closeEvent(self, event):
            if all_hardware and not self._close_after_cleanup:
                self.laser_panel.request_shutdown()
            if self.any_busy():
                if "Alignment" in self.pages:
                    self.pages["Alignment"]._workspace_closing = True
                if not self._close_after_cleanup:
                    self.stop_all()
                    self.analysis_panel.cancel_load()
                self._close_after_cleanup = True
                self._close_retry.start()
                self.overview_status.setText("Stopping; window will close after cleanup")
                self.tabs.setCurrentIndex(0)
                self.details_toggle.setChecked(True)
                self.report.setPlainText("Waiting for running jobs. Retained saves are allowed to finish; other work is stopping.")
                event.ignore()
                return
            self._close_retry.stop()
            self._close_after_cleanup = False
            if "Alignment" in self.pages:
                self.pages["Alignment"]._workspace_closing = False
            if not self.save_preferences():
                from PyQt6.QtWidgets import QMessageBox

                answer = QMessageBox.question(self, "Settings not saved", "Close without saving operator settings?",
                                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                              QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            if all_hardware and self.laser_panel.model.connected:
                self.overview_status.setText("Laser disconnect failed; inspect error and retry Disconnect before closing")
                event.ignore()
                return
            if not self.camera_window.close():
                event.ignore()
                return
            if not close_workflows(self.pages):
                event.ignore()
                return
            if hasattr(self, "workspace_hub"):
                self.workspace_hub.shutdown()
            if all_hardware:
                self.laser_panel.close()
            if hasattr(self, "stage_window"):
                try:
                    self.stage_window.shutdown()
                except Exception as error:  # noqa: BLE001 - veto window close if stage cleanup fails
                    self.overview_status.setText("Stage disconnect failed: " + str(error))
                    event.ignore()
                    return
            if not self.analysis_panel.shutdown():
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
