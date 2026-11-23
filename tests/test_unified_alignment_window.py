"""Actual Qt workspace integration with fake transports; no physical devices."""

import builtins
import shutil
import time
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
from PyQt6.QtWidgets import QApplication, QMessageBox
from test_operator_spectrum_runtime import FakeSpectrometer

from labtools.gui.native_workspace import create_window
from labtools.runtime.hardware_spectrum_workspace import HardwareSpectrumWorkspace
from labtools.runtime.session import ResourceBusyError
from labtools.simulation.operator_session import SimulatedOperatorSession

ROOT = Path(__file__).resolve().parents[1]


def spin(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Unified alignment lifecycle timed out"
        time.sleep(0.002)
    app.processEvents()


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    dialogs = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: dialogs.append(self.text()) or 0)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    rig = SimpleNamespace(events=[], frames=0, cleaning=Event(), allow_cleanup=Event(), fail_capture=False, fail_cleanup=False)
    rig.allow_cleanup.set()
    workspace = HardwareSpectrumWorkspace(
        tmp_path / "bundle/candidate.json", preferences_path=tmp_path / "prefs.json",
        spectrometer_factory=lambda **kwargs: FakeSpectrometer(rig=rig, **kwargs),
    )
    widget = create_window(workspace)
    widget.show()
    app.processEvents()
    yield app, widget, workspace, rig, dialogs
    rig.allow_cleanup.set()
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    widget.close()
    spin(app, lambda: workspace._closed)
    assert not workspace._operator_spectrum.worker.is_alive()


def test_alignment_is_styled_embedded_and_native_launch_is_idle(window):
    _, widget, workspace, rig, _ = window
    alignment = widget.pages["Alignment"]
    assert widget.tabs.tabText(3) == "Alignment"
    assert alignment._worker is workspace._operator_spectrum.worker
    assert not alignment._owns_worker
    assert alignment.setup_group.objectName() == "studioCard"
    assert alignment._parameter_wheel_guard is not None
    assert widget.mode_badge.text() == "Real HORIBA"
    assert not widget.pages["Intensity map"].start_button.isEnabled()
    assert not widget.pages["Annealing"].start_button.isEnabled()
    assert not widget.laser_panel.connect_button.isEnabled()
    assert widget.pages["Spectrum"].acquire_button.isEnabled()
    widget.refresh_button.click()
    assert "real HORIBA" in widget.overview_status.text()
    assert not rig.events
    assert workspace._operator_spectrum.worker.status().state == "unopened"


def test_alignment_blocks_spectrum_then_stop_all_allows_range_and_restart(window):
    app, widget, workspace, rig, _ = window
    alignment = widget.pages["Alignment"]
    spectrum = widget.pages["Spectrum"]
    alignment.start_alignment()
    spin(app, lambda: alignment._sequence >= 3)
    assert [event[0] for event in rig.events].count("connect") == 1
    spectrum.test_spectrometer_connection()
    assert not spectrum._async_tasks
    assert "busy" in spectrum.status.text().lower()
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    assert workspace._operator_spectrum.worker.is_alive()
    spectrum.test_spectrometer_connection()
    spin(app, lambda: not spectrum._async_tasks)
    assert "disconnected" in spectrum.status.text().lower()
    alignment.start_alignment()
    spin(app, lambda: alignment._sequence >= 1)
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())


def test_spectrum_lease_refuses_alignment_without_opening_device(window):
    _, widget, workspace, rig, _ = window
    lease = workspace._ownership.reserve("Spectrum")
    try:
        widget.pages["Alignment"].start_alignment()
        assert "busy" in widget.pages["Alignment"].status_label.text().lower()
        assert widget.pages["Alignment"]._job is None
        assert not rig.events
    finally:
        lease.release()


def test_close_waits_for_cleanup_then_closes_worker_automatically(window):
    app, widget, workspace, rig, dialogs = window
    rig.allow_cleanup.clear()
    alignment = widget.pages["Alignment"]
    alignment.start_alignment()
    spin(app, lambda: alignment._sequence >= 1)
    assert not widget.close()
    spin(app, rig.cleaning.is_set)
    assert widget.isVisible() and not workspace._closed
    assert alignment._workspace_lease is not None
    with pytest.raises(ResourceBusyError):
        workspace._ownership.reserve("Spectrum")
    rig.allow_cleanup.set()
    spin(app, lambda: workspace._closed)
    assert not widget.isVisible()
    assert not dialogs


@pytest.mark.parametrize("closing", [False, True])
def test_failed_disconnect_is_faulted_and_close_has_no_late_modal(window, closing):
    app, widget, workspace, rig, dialogs = window
    rig.fail_cleanup = True
    alignment = widget.pages["Alignment"]
    alignment.start_alignment()
    spin(app, lambda: alignment._sequence >= 1)
    if closing:
        widget.close()
        spin(app, lambda: workspace._closed)
        assert not dialogs
    else:
        widget.stop_all()
        spin(app, lambda: not widget.any_busy())
        assert workspace._operator_spectrum.worker.status().state == "faulted"
        assert "teardown" in alignment.status_label.text()
        assert not alignment.start_button.isEnabled()
        widget.pages["Spectrum"].test_spectrometer_connection()
        assert "teardown" in widget.pages["Spectrum"].status.text()
        assert len(dialogs) == 1


def test_simulated_unified_alignment_never_imports_native(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("labtools.devices", "horiba_sdk")):
            raise AssertionError("Native import in simulated workspace: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    workspace = SimulatedOperatorSession(tmp_path / "bundle/candidate.json", preferences_path=tmp_path / "sim.json")
    widget = create_window(workspace)
    try:
        widget.show()
        alignment = widget.pages["Alignment"]
        alignment.start_alignment()
        spin(app, lambda: alignment._sequence >= 2)
        widget.stop_all()
        spin(app, lambda: not widget.any_busy())
        assert workspace._operator_spectrum.worker.status().state == "available"
    finally:
        widget.stop_all()
        spin(app, lambda: not widget.any_busy())
        widget.close()
        app.processEvents()
    assert workspace._closed
