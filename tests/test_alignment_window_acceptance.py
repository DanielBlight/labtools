"""Offscreen blocked-job acceptance for the real alignment window with fake backends."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
from PyQt6.QtWidgets import QApplication, QMessageBox
from test_alignment_lifecycle_acceptance import BlockedBackend

from labtools.acquisition.alignment_spectrum import AlignmentSettings
from labtools.acquisition.spectrum_service import SpectrumService
from labtools.gui.alignment_gui_horiba import HoribaAlignmentWindow
from labtools.runtime.spectrum_worker import SpectrumWorker


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def spin(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Alignment lifecycle timed out"
        time.sleep(0.001)
    app.processEvents()


@pytest.fixture
def window(app, monkeypatch):
    backend = BlockedBackend()
    worker = SpectrumWorker(
        SpectrumService(lambda s: None, backend.open), backend="real"
    )
    dialogs = []
    monkeypatch.setattr(
        QMessageBox, "exec", lambda self: dialogs.append(self.text()) or 0
    )
    widget = HoribaAlignmentWindow(
        worker=worker, configuration_id="test", backend="real"
    )
    widget.show()
    yield widget, worker, backend, dialogs
    backend.unblock()
    if widget._job is not None:
        widget.stop_alignment()
        spin(app, lambda: widget._job is None)
    widget.close()
    worker.close()
    app.processEvents()
    assert not worker.is_alive()
    assert not widget.timer.isActive()


def test_stop_then_programmatic_restart_cannot_replace_owned_job(app, window):
    widget, worker, backend, _ = window
    widget.start_alignment()
    spin(app, backend.entered.is_set)
    job = widget._job
    widget.stop_alignment()
    widget.start_alignment()
    assert widget._job is job
    assert not widget.start_button.isEnabled()
    backend.release.set()
    spin(app, backend.cleaning.is_set)
    assert worker.status().state == "busy"
    assert widget._job is job
    backend.release_cleanup.set()
    spin(app, lambda: widget._job is None)
    assert widget.status_label.text() == "Stopped"
    assert widget.start_button.isEnabled()
    assert not widget.timer.isActive()
    widget.start_alignment()
    spin(app, lambda: widget._sequence >= 1)
    widget.stop_alignment()
    spin(app, lambda: widget._job is None)


def test_other_owner_busy_is_recoverable_without_duplicate_open(app, window):
    widget, worker, backend, _ = window
    external = worker.acquire_alignment(
        AlignmentSettings("test"), owner="other-spectrum"
    )
    try:
        spin(app, backend.entered.is_set)
        widget.start_alignment()
        assert "other-spectrum" in widget.status_label.text()
        assert widget.start_button.isEnabled()
        assert widget._job is None
        assert not widget.timer.isActive()
        assert worker.status().state == "busy"
        assert len(backend.requests) == 1
        assert sum(e[0] == "cleanup-start" for e in backend.events) == 0
    finally:
        backend.unblock()
        external.result(3)
    widget.start_alignment()
    spin(app, lambda: widget._sequence >= 1)
    widget.stop_alignment()
    spin(app, lambda: widget._job is None)


def test_injected_close_waits_for_cleanup_and_does_not_close_worker(app, window):
    widget, worker, backend, dialogs = window
    widget.start_alignment()
    spin(app, backend.entered.is_set)
    assert not widget.close()
    job = widget._job
    widget.start_alignment()
    assert widget._job is job
    backend.release.set()
    spin(app, backend.cleaning.is_set)
    assert widget.isVisible()
    assert worker.status().state == "busy"
    backend.release_cleanup.set()
    spin(app, lambda: not widget.isVisible())
    assert worker.status().state == "available"
    assert worker.is_alive()
    assert widget._job is None and not widget.timer.isActive()
    assert not dialogs
    widget.start_alignment()
    assert widget._job is None


@pytest.mark.parametrize(
    "failure", ["connect", "configure", "move", "dark", "capture", "disconnect"]
)
def test_fault_disables_restart_only_after_cleanup(app, window, failure):
    widget, worker, backend, dialogs = window
    backend.failure = failure
    widget.dark_checkbox.setChecked(True)
    widget.start_alignment()
    backend.release.set()
    spin(app, backend.cleaning.is_set)
    assert worker.status().state == "busy"
    assert not widget.start_button.isEnabled()
    backend.release_cleanup.set()
    spin(app, lambda: widget._job is None)
    assert worker.status().state == "faulted"
    assert "teardown" in widget.status_label.text()
    assert not widget.start_button.isEnabled()
    events = list(backend.events)
    widget.start_alignment()
    assert widget._job is None and backend.events == events
    assert len(dialogs) == 1


def test_close_during_failure_does_not_open_modal_after_close(app, window):
    widget, worker, backend, dialogs = window
    backend.failure = "capture"
    widget.start_alignment()
    spin(app, backend.entered.is_set)
    assert not widget.close()
    backend.release.set()
    spin(app, backend.cleaning.is_set)
    backend.release_cleanup.set()
    spin(app, lambda: not widget.isVisible())
    assert worker.status().state == "faulted"
    assert not dialogs


def test_private_worker_is_closed_once_after_deferred_close(app, monkeypatch):
    import labtools.gui.alignment_gui_horiba as gui

    backend = BlockedBackend()
    monkeypatch.setattr(
        gui,
        "create_spectrum_service",
        lambda **kw: SpectrumService(lambda s: None, backend.open),
    )
    widget = HoribaAlignmentWindow(configuration_id="test", backend="real")
    worker = widget._worker
    closes = []
    original_close = worker.close

    def close():
        closes.append(1)
        original_close()

    monkeypatch.setattr(worker, "close", close)
    widget.show()
    try:
        widget.start_alignment()
        spin(app, backend.entered.is_set)
        assert not widget.close()
        backend.release.set()
        spin(app, backend.cleaning.is_set)
        assert not closes
        backend.release_cleanup.set()
        spin(app, lambda: not widget.isVisible())
        assert closes == [1]
        assert worker.status().state == "closed"
        assert not worker.is_alive()
        assert not widget.timer.isActive()
    finally:
        backend.unblock()
        if widget._job is not None:
            spin(app, lambda: widget._job is None)
        original_close()
        widget.close()


def test_settings_snapshot_and_result_identity_stay_on_correct_boundary(
    app, window, monkeypatch
):
    from threading import get_ident

    import numpy as np

    widget, _worker, backend, _ = window
    gui_thread = get_ident()
    original = widget._snapshot_settings
    snapshots = []

    def snapshot():
        assert get_ident() == gui_thread
        settings = original()
        snapshots.append(settings)
        return settings

    monkeypatch.setattr(widget, "_snapshot_settings", snapshot)
    widget.exposure_box.setValue(0.2)
    widget.start_alignment()
    spin(app, backend.entered.is_set)
    assert len(snapshots) == 1
    assert backend.requests[0] is snapshots[0]
    widget.exposure_box.setValue(
        0.3
    )  # programmatic edit must not mutate submitted data
    backend.unblock()
    spin(app, lambda: widget._latest is not None)
    widget.stop_alignment()
    spin(app, lambda: widget._job is None)
    assert widget._latest.settings.exposure_s == 0.2
    assert all(request.exposure_s == 0.2 for request in backend.requests)
    np.testing.assert_array_equal(widget.line.get_xdata(), widget._latest.wavelength_nm)
    np.testing.assert_array_equal(widget.line.get_ydata(), widget._latest.intensity)
    np.testing.assert_array_equal(widget._latest.raw_intensity, [5.0])
    assert all(event[1] != gui_thread for event in backend.events)
