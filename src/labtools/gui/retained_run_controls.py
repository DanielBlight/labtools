"""Unified optional output, retained-result export and compact Annealing layout."""

from threading import Lock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from labtools.gui.workspace_studio import add_card, scroll_content
from labtools.runtime.retained_results import export_retained


class Retention:
    def __init__(self):
        self.lock = Lock()
        self.value = None

    def set(self, value):
        with self.lock:
            self.value = value

    def get(self):
        with self.lock:
            return self.value


def save_button(panel, retention, busy, label):
    button = QPushButton("Save results…")
    button.setToolTip("Save the retained run without reacquisition. Save before a replacement run or closing the application.")
    def save():
        if busy():
            panel.set_status("Wait for acquisition and cleanup before saving retained results") if hasattr(panel, "set_status") else panel.status.setText("Wait for cleanup")
            return
        value = retention.get()
        if value is None:
            return
        folder = QFileDialog.getExistingDirectory(panel, "Save retained " + label)
        if not folder:
            return
        try:
            target = export_retained(folder, value, label=label)
            text = "Saved retained run: " + str(target)
        except (OSError, ValueError, TypeError) as error:
            text = "Save failed; retained run is unchanged: " + str(error)
        if hasattr(panel, "set_status"):
            panel.set_status(text)
        else:
            panel.status.setText(text)
    button.clicked.connect(save)
    timer = QTimer(button)
    timer.setInterval(150)
    timer.timeout.connect(lambda: button.setEnabled(not busy() and retention.get() is not None))
    timer.start()
    button.setEnabled(False)
    return button


def wrap_acquisition(original, retention, *, map_mode=False):
    def acquire(config, **kwargs):
        events = []
        latest = None
        retention.set(None)
        callback = kwargs.get("progress_callback")
        def progress(event):
            nonlocal latest
            latest = event
            # Maps already retain their full arrays in the final result. Anneal
            # progress records executed coordinates/times for post-run export.
            if not map_mode:
                events.append(event)
            if callback is not None:
                callback(event)
        kwargs["progress_callback"] = progress
        if map_mode:
            kwargs["memory_only"] = not config.save_results
        try:
            result = original(config, **kwargs)
        except BaseException as error:
            retention.set({"settings": config, "progress": events, "latest_progress": latest, "status": "failed", "error": repr(error)})
            raise
        retention.set({"settings": config, "progress": events, "result": result})
        return result
    return acquire


def find_card(panel, title):
    for label in panel.findChildren(QLabel):
        if label.text() == title and label.parentWidget().objectName() == "studioCard":
            return label.parentWidget()
    raise RuntimeError("Expected Annealing card not found: " + title)


def annealing_layout(window, program, save):
    panel = window.pages["Annealing"]
    scan, dose, output = (find_card(panel, title) for title in ("Scan", "Dose program", "Output"))
    central = QWidget()
    root = QVBoxLayout(central)
    root.setContentsMargins(0, 14, 0, 0)
    heading = QLabel("Annealing")
    heading.setObjectName("studioTitle")
    root.addWidget(heading)
    columns = QHBoxLayout()
    root.addLayout(columns, 1)
    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(0, 0, 0, 0)
    scroll, content = scroll_content()
    left_layout.addWidget(scroll)
    content.addWidget(dose)
    content.addWidget(scan)
    content.addWidget(program.preview_button)
    content.addWidget(program.log)
    content.addStretch(1)
    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    instruments = add_card(right_layout, "Instruments", [
        ("Shutter port", panel.sc10_port), (None, panel.test_sc10), (None, panel.shutter_state),
        ("Anneal coordinate", panel.anneal_stage_coordinate), (None, panel.move_to_anneal_stage),
        (None, panel.return_stage), ("Return coordinate", panel.return_stage_coordinate), (None, panel.test_stage),
    ])
    right_layout.addWidget(output)
    right_layout.addWidget(save)
    right_layout.addStretch(1)
    columns.addWidget(left, 1)
    columns.addWidget(right, 1)
    root.addWidget(panel.estimate)
    buttons = QHBoxLayout()
    buttons.addWidget(panel.start_button)
    buttons.addWidget(panel.stop_button)
    root.addLayout(buttons)
    root.addWidget(panel.status)
    # Reparent all reused controls before the old central widget is retired.
    panel.setCentralWidget(central)
    panel.instruments_card = instruments
    panel.output_card = output
    dose.show()
    scan.show()
    output.show()
    panel.save_log.setText("Save results to disk")
    panel.save_log.toggled.connect(panel.output_root.setEnabled)
    browse = next((b for b in output.findChildren(QPushButton) if b.text() == "Browse"), None)
    if browse is not None:
        panel.save_log.toggled.connect(browse.setEnabled)
        browse.setEnabled(panel.save_log.isChecked())
    panel.output_root.setEnabled(panel.save_log.isChecked())
    def reflect():
        if program.busy:
            panel.status.setText(program.status.text())
        if program.last_result is not None:
            panel.retained_run.set({"settings": program.run_settings, "result": program.last_result})
    program.timer.timeout.connect(reflect)


def install_retained_controls(window):
    mapping = window.pages["Intensity map"]
    mapping.retained_run = Retention()
    mapping.map_controller._acquisition = wrap_acquisition(mapping.map_controller._acquisition, mapping.retained_run, map_mode=True)
    def map_finished(result):
        if not mapping.retained_run.get()["settings"].save_results:
            mapping.set_status("Map completed; results retained in memory" if result.complete else "Map stopped; partial results retained in memory")
    mapping.map_controller.finished.connect(map_finished)
    mapping.save_retained_button = save_button(mapping, mapping.retained_run, lambda: mapping.map_controller.busy, "intensity-map")
    mapping.centralWidget().layout().insertWidget(1, mapping.save_retained_button)
    spectrum = window.pages["Spectrum"]
    spectrum.retained_run = Retention()
    spectrum.save_retained_button = save_button(spectrum, spectrum.retained_run, lambda: bool(spectrum._async_tasks), "spectrum")
    spectrum.centralWidget().layout().insertWidget(1, spectrum.save_retained_button)
    original = spectrum._handle_acquire_done
    def done(result):
        spectrum.retained_run.set(result)
        original(result)
    spectrum._handle_acquire_done = done
    anneal = window.pages["Annealing"]
    anneal.retained_run = Retention()
    anneal._acquisition = wrap_acquisition(anneal._acquisition, anneal.retained_run)
    anneal.save_retained_button = save_button(anneal, anneal.retained_run,
        lambda: anneal._thread is not None or window.pages["Anneal programs"].busy, "annealing")
    annealing_layout(window, window.pages["Anneal programs"], anneal.save_retained_button)
