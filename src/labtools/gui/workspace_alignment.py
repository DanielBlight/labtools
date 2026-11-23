"""Alignment panel reusing the accepted stream and workspace Spectrum lease."""

from copy import deepcopy

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from labtools.gui.alignment_gui_horiba import HoribaAlignmentWindow, NavigationToolbar
from labtools.gui.workspace_studio import (
    StudioSplit,
    add_card,
    new_page,
    scroll_content,
)
from labtools.runtime.session import ResourceBusyError


class WorkspaceAlignmentPanel(HoribaAlignmentWindow):
    def __init__(self, *, workspace, runtime):
        self.workspace = workspace
        self._runtime = runtime
        self._workspace_lease = None
        options = deepcopy(workspace.plan.hardware_settings["detectors"])
        super().__init__(
            worker=runtime.worker, configuration_id=workspace.plan.configuration_id,
            backend=runtime.backend, options_provider=lambda preset: deepcopy(options[preset]),
        )
        self.status = self.status_label
        self.dark_checkbox.setText("Subtract a fresh dark per frame")
        self.toolbar = self.findChild(NavigationToolbar)
        self._install_view()
        settings = workspace.drafts.values["spectrum"]
        self.preset_combo.setCurrentText(settings.preset)
        self.exposure_box.setValue(settings.exposure_s)
        self.gain_combo.setCurrentIndex(self.gain_combo.findData(settings.gain))
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(settings.speed))
        self.centre_box.setValue((settings.start_nm + settings.end_nm) / 2)
        if workspace.drafts.alignment:
            from labtools.gui.workspace_hub import apply_alignment
            from labtools.runtime.workspace_settings import validate_alignment

            try:
                apply_alignment(self, validate_alignment(workspace, workspace.drafts.alignment))
            except (ValueError, TypeError, KeyError) as error:
                workspace.drafts.store.messages.append("Alignment preferences ignored: " + str(error))

    def _install_view(self):
        layout = new_page(self, "Alignment")
        split = StudioSplit()
        layout.addWidget(split, 1)
        left = QWidget()
        controls = QVBoxLayout(left)
        controls.setContentsMargins(0, 0, 0, 0)
        scroll, content = scroll_content()
        controls.addWidget(scroll, 1)
        self.setup_group = add_card(content, "Continuous acquisition", [
            ("Detector", self.preset_combo), ("Centre wavelength (nm)", self.centre_box),
            ("Exposure", self.exposure_box), ("Gain", self.gain_combo),
            ("Readout", self.speed_combo), (None, self.dark_checkbox),
        ])
        note = QLabel("One connection per Start. Stop before changing acquisition settings.")
        note.setWordWrap(True)
        content.addWidget(note)
        content.addStretch(1)
        buttons = QHBoxLayout()
        self.start_button.setText("Start alignment")
        self.start_button.setObjectName("primaryButton")
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        controls.addLayout(buttons)
        controls.addWidget(self.status_label)
        right = QFrame()
        right.setObjectName("studioCard")
        plot = QVBoxLayout(right)
        plot.addWidget(self.toolbar)
        plot.addWidget(self.canvas, 1)
        plot.addWidget(self.autoscale)
        plot.addWidget(self.metrics)
        split.addWidget(left)
        split.addWidget(right)

    def _snapshot_settings(self):
        return self._runtime.validate_alignment(super()._snapshot_settings())

    def start_alignment(self):
        if self._running or self._job is not None or self._closed or self._close_pending:
            return
        try:
            self._workspace_lease = self.workspace._ownership.reserve("Spectrum")
        except ResourceBusyError as error:
            self.status_label.setText(f"Workspace busy: {error}")
            return
        try:
            super().start_alignment()
        finally:
            if self._job is None:
                self._release_lease()

    def _release_lease(self):
        if self._workspace_lease is not None:
            self._workspace_lease.release()
            self._workspace_lease = None

    def _finish(self, message):
        # The base method is reached only after job completion, or start refusal.
        self._release_lease()
        super()._finish(message)

    def _report_job_failure(self):
        if getattr(self, "_workspace_closing", False):
            self._finish("Alignment failed; application teardown is required")
        else:
            super()._report_job_failure()

    def request_stop(self):
        self.stop_alignment()

    def closeEvent(self, event):
        if not getattr(self, "_workspace_closing", False):
            if self._job is not None:
                self._close_pending = True
                self.stop_alignment()
                event.ignore()
                return
            self._close_pending = False
            self._closed = False
            self.hide()
            event.accept()
            return
        super().closeEvent(event)
        if event.isAccepted():
            self._release_lease()
