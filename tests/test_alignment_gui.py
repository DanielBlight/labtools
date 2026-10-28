"""Offscreen alignment window lifecycle through an injected SpectrumWorker."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
from PyQt6.QtWidgets import QApplication, QMessageBox

from labtools.gui.alignment_gui_horiba import HoribaAlignmentWindow
from labtools.runtime.spectrum_backend import create_spectrum_service
from labtools.runtime.spectrum_worker import SpectrumWorker


def options(preset):
    return {
        "gains": (("gain", 2),),
        "speeds": (("speed", 0),),
        "default_gain": 2,
        "default_speed": 0,
        "minimum_exposure_s": 0.065 if preset == "syncerity" else 0.1,
    }


def spin(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline
        time.sleep(0.002)
    app.processEvents()


def test_injected_worker_repeat_stop_and_close(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    worker = SpectrumWorker(
        create_spectrum_service(backend="simulation"), backend="simulation"
    )
    w = HoribaAlignmentWindow(
        worker=worker,
        configuration_id="test",
        backend="simulation",
        options_provider=options,
    )
    assert worker.status().state == "unopened"
    assert w.exposure_box.minimum() == pytest.approx(0.065)
    w.preset_combo.setCurrentText("symphony")
    assert w.exposure_box.minimum() == pytest.approx(0.1)
    w.show()
    w.start_alignment()
    spin(app, lambda: w._sequence >= 2)
    w.stop_alignment()
    spin(app, lambda: not w._running and w._job is None)
    assert worker.status().state == "available" and worker.is_alive()
    w.start_alignment()
    spin(app, lambda: w._sequence >= 1)
    assert not w.close()
    spin(app, lambda: not w.isVisible())
    assert worker.is_alive()  # injected/application-owned
    worker.close()
