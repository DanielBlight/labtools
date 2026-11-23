"""Actual Qt hub, real-mode controls and close lifecycle with injected hardware."""

import json
import shutil
import time
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

import pytest

pytest.importorskip("PyQt6.QtWidgets", exc_type=ImportError)
from PyQt6.QtWidgets import QApplication, QMessageBox
from test_all_hardware_runtime import FakeLaser

from labtools.config.anneal_workspace import InstrumentProfile
from labtools.config.native_candidate import preflight_candidate
from labtools.gui.native_workspace import create_window
from labtools.runtime.hardware_workspace import HardwareWorkspace
from labtools.runtime.session import ResourceBusyError
from labtools.simulation.operator_session import SimulatedOperatorSession
from labtools.simulation.transport_fakes import (
    TransportTrace,
    map_factories,
    spectrum_factory,
)

ROOT = Path(__file__).resolve().parents[1]


def spin(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "Hardware window lifecycle timed out"
        time.sleep(0.002)
    app.processEvents()


@pytest.fixture
def window(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest = tmp_path / "bundle/candidate.json"
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(asdict(InstrumentProfile(profile_id="test-reviewed", approved=True))))
    plan = preflight_candidate(manifest).plan
    trace = TransportTrace()
    events = []
    laser_devices = []
    auxiliary_entered, auxiliary_release = Event(), Event()
    auxiliary_release.set()
    anneal_entered = Event()

    def laser():
        device = FakeLaser(events)
        laser_devices.append(device)
        return device

    def auxiliary(action, config, coordinate):
        auxiliary_entered.set()
        assert auxiliary_release.wait(5)
        return "Fake diagnostic complete"

    def anneal(config, *, stop_event=None, **kwargs):
        from labtools.config.anneal_types import LaserAnnealResult

        anneal_entered.set()
        stop_event.wait(0.1)
        return LaserAnnealResult(completed=not stop_event.is_set(), completed_points=1, total_points=config.total_points, stopped=stop_event.is_set(),
                                 elapsed_s=0.1, output_directory=None)

    workspace = HardwareWorkspace(manifest, anneal_profile=profile, preferences_path=tmp_path / "prefs.json",
                                  map_factories=map_factories(plan.map_config, trace),
                                  spectrometer_factory=spectrum_factory(plan.spectrum_request.settings, trace),
                                  laser_factory=laser, auxiliary_action=auxiliary, anneal_acquisition=anneal)
    workspace.drafts.values["anneal"] = replace(workspace.drafts.values["anneal"], output_root=tmp_path / "anneal")
    widget = create_window(workspace)
    widget.show()
    app.processEvents()
    yield app, widget, workspace, events, laser_devices, auxiliary_entered, auxiliary_release, anneal_entered
    auxiliary_release.set()
    if laser_devices:
        laser_devices[-1].fail_close = False
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    widget.close()
    spin(app, lambda: workspace._closed)


def test_all_hardware_controls_are_enabled_without_connecting(window):
    _, widget, workspace, events, _, _, _, _ = window
    assert widget.mode_badge.text() == "Real hardware"
    assert widget.pages["Intensity map"].start_button.isEnabled()
    assert widget.pages["Annealing"].start_button.isEnabled()
    assert widget.pages["Annealing"].test_sc10.isEnabled()
    assert widget.pages["Annealing"].test_stage.isEnabled()
    assert widget.laser_panel.connect_button.isEnabled()
    assert widget.laser_panel.current.maximum() == 0.04
    assert widget.workspace_hub.mode.text() == "All real hardware"
    assert widget.workspace_hub.device_table.rowCount() >= 7
    assert not events
    assert workspace._operator_spectrum.worker.status().state == "unopened"


def test_laser_stop_all_and_close_disconnect_asynchronously(window):
    app, widget, workspace, events, _, _, _, _ = window
    widget.laser_panel.command("connect")
    spin(app, lambda: not widget.laser_panel.busy)
    assert workspace.laser.connected and workspace.laser.output is False
    assert not any(action == "on" for action, _ in events)
    with pytest.raises(RuntimeError):
        widget.workspace_hub.require_idle(switching=True)
    widget.laser_panel.command("on")
    spin(app, lambda: not widget.laser_panel.busy)
    assert workspace.laser.output is True
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    assert workspace.laser.output is False
    widget.close()
    spin(app, lambda: workspace._closed)
    assert not workspace.laser.connected
    assert any(action == "close" for action, _ in events)


def test_auxiliary_diagnostic_holds_lease_and_defers_parent_close(window):
    app, widget, workspace, _, _, entered, release, _ = window
    release.clear()
    panel = widget.pages["Annealing"]
    panel._test_rotation_stage()
    spin(app, entered.is_set)
    assert widget.any_busy()
    with pytest.raises(ResourceBusyError):
        workspace._ownership.reserve("Spectrum")
    assert not widget.close()
    assert widget.isVisible() and not workspace._closed
    release.set()
    spin(app, lambda: workspace._closed)


def test_anneal_start_is_real_worker_bound_and_stop_all_releases_lease(window):
    app, widget, workspace, _, _, _, _, entered = window
    panel = widget.pages["Annealing"]
    panel._start()
    spin(app, entered.is_set)
    assert panel._workspace_lease is not None
    widget.stop_all()
    spin(app, lambda: not widget.any_busy())
    assert panel._workspace_lease is None
    assert "Anneal" in panel.status.text() and "failed" not in panel.status.text().lower()
    assert all(state.owner is None for state in workspace._ownership.status().resources)


def test_settings_export_load_and_startup_restore_include_alignment(window, tmp_path):
    app, widget, workspace, _, _, _, _, _ = window
    hub = widget.workspace_hub
    panel = widget.pages["Alignment"]
    panel.centre_box.setValue(701.0)
    panel.exposure_box.setValue(0.2)
    path = tmp_path / "workflow.json"
    hub.export_settings(path)
    panel.centre_box.setValue(800.0)
    hub.load_settings(path)
    assert panel.centre_box.value() == 701.0
    assert panel.exposure_box.value() == 0.2
    data = json.loads(path.read_text())
    data["workflows"]["map"]["mirror_dio_pin"] = 999
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        hub.load_settings(path)
    assert panel.centre_box.value() == 701.0
    assert widget.save_preferences()
    assert workspace.drafts.store.read()["alignment"]["centre_nm"] == 701.0
    lease = workspace._ownership.reserve("Spectrum")
    try:
        with pytest.raises(RuntimeError):
            hub.require_idle(switching=True)
    finally:
        lease.release()
    widget.close()
    spin(app, lambda: workspace._closed)
    replacement = HardwareWorkspace(workspace.manifest, anneal_profile=next(s.path for s in workspace.plan.sources if s.field == "local_anneal_profile"),
                                    preferences_path=workspace.drafts.store.path)
    second = create_window(replacement)
    try:
        assert second.pages["Alignment"].centre_box.value() == 701.0
    finally:
        second.close()
        app.processEvents()


def test_idle_configuration_switch_rebuilds_same_mode_without_native_imports(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "one")
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "two")
    workspace = SimulatedOperatorSession(tmp_path / "one/candidate.json", preferences_path=tmp_path / "prefs.json")
    widget = create_window(workspace)
    widget.show()
    assert widget.workspace_hub.switch_configuration(tmp_path / "two/candidate.json")
    replacement = widget._replacement_window
    try:
        assert workspace._closed
        assert replacement.workspace_hub.workspace.simulation_only
        assert replacement.workspace_hub.workspace.manifest == tmp_path / "two/candidate.json"
    finally:
        replacement.close()
        app.processEvents()


def test_failed_laser_close_keeps_window_and_controls_available_for_retry(window):
    app, widget, workspace, _, devices, _, _, _ = window
    widget.laser_panel.command("connect")
    spin(app, lambda: not widget.laser_panel.busy)
    devices[-1].fail_close = True
    widget.close()
    spin(app, lambda: not widget.any_busy())
    # Process the automatic deferred-close attempt.
    deadline = time.monotonic() + 0.1
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.002)
    assert widget.isVisible() and not workspace._closed
    assert widget.laser_panel.disconnect_button.isEnabled()
    assert widget.pages["Intensity map"].isVisible() or widget.tabs.indexOf(widget.pages["Intensity map"]) >= 0
    devices[-1].fail_close = False
    widget.laser_panel.command("disconnect")
    spin(app, lambda: not widget.any_busy())
    widget.close()
    spin(app, lambda: workspace._closed)


def test_hub_map_diagnostic_holds_lease_and_releases_after_completion(window):
    app, widget, workspace, _, _, _, _, _ = window
    widget.workspace_hub.test_map()
    assert widget.workspace_hub.busy
    spin(app, lambda: not widget.any_busy())
    assert "tested" in widget.workspace_hub.message.text().lower()
    assert all(state.owner is None for state in workspace._ownership.status().resources)


def test_configuration_change_is_refused_during_active_diagnostic(window):
    app, widget, workspace, _, _, entered, release, _ = window
    release.clear()
    widget.pages["Annealing"]._test_sc10()
    spin(app, entered.is_set)
    with pytest.raises(RuntimeError):
        widget.workspace_hub.switch_configuration(workspace.manifest)
    assert not workspace._closed
    release.set()
    spin(app, lambda: not widget.any_busy())
