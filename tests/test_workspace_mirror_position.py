"""Header mirror popup and baseline/post-anneal spectrum position contracts."""

import asyncio
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from threading import Event

import numpy as np
import pytest
from PyQt6.QtWidgets import QHBoxLayout
from test_experiment_panels import spin
from test_experiment_workflows import program

from labtools.runtime.experiment_workflows import run_sequence
from labtools.runtime.workflow_batch import Batch
from labtools.runtime.workspace_mirror import (
    move_manual,
    positioned_spectrum,
    validate_position,
)

pytest_plugins = ["test_experiment_panels", "test_experiment_workflows"]
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("position", [(float('nan'), 0, 0), (0, float('inf'), 0), (11, 0, 0), (0, 0, -1), (0, 0, 61), (True, 0, 0)])
def test_invalid_positions_before_io(workspace, position):
    with pytest.raises(ValueError):
        validate_position(workspace, *position)
    assert not hasattr(workspace, '_mirror_last_commanded')


def test_manual_move_requires_shared_lease_and_no_implicit_home(workspace):
    with pytest.raises(PermissionError):
        move_manual(workspace, .2, -.3)
    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
    try:
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"):
            result = move_manual(workspace, .2, -.3)
        assert workspace._mirror_last_commanded == (.2, -.3)
        assert 'not readback' in result['position_kind']
    finally:
        batch.release()


def test_positioned_spectrum_and_sequence_metadata(workspace, tmp_path):
    result = run_sequence(workspace, program(workspace), "Spectrum", workspace.workflows.spectrum_settings(),
        cycles=2, save_output=False, spectrum_position=(.2, -.3, 0))
    assert result['spectrum_position'] == (.2, -.3, 0)
    assert len(result['retained_steps']) == 5
    assert result['retained_steps'][0]['role'] == 'baseline'
    source = workspace.plan.hardware_settings
    assert workspace._mirror_last_commanded == (source['home_x_voltage_v'], source['home_y_voltage_v'])
    assert all(s.owner is None for s in workspace._ownership.status().resources)


def test_cancel_before_position_does_not_move(workspace):
    stop = Event()
    stop.set()
    batch = Batch(workspace._ownership, ("Spectrum", "Intensity map"))
    try:
        with batch.borrow("Spectrum"), batch.borrow("Intensity map"), pytest.raises(asyncio.CancelledError):
            positioned_spectrum(workspace, workspace.workflows.spectrum_settings(), (.1, .2, 0), stop=stop)
        assert not hasattr(workspace, '_mirror_last_commanded')
    finally:
        batch.release()


def test_popup_header_no_move_open_close_reopen(window):
    app, widget, workspace = window
    popup = widget.mirror_window
    assert not popup.isVisible() and not hasattr(workspace, '_mirror_last_commanded')
    layout = next(l for l in widget.findChildren(QHBoxLayout) if l.indexOf(widget.camera_button) >= 0)
    assert layout.indexOf(widget.mirror_button) == layout.indexOf(widget.camera_button) + 1
    widget.mirror_button.click()
    assert popup.isVisible() and popup.isWindow()
    popup.x.setValue(.1)
    popup.y.setValue(-.2)
    popup.start_button.click()
    spin(app, lambda: not popup.busy)
    assert workspace._mirror_last_commanded == (.1, -.2)
    popup.close()
    assert workspace._mirror_last_commanded == (.1, -.2)
    widget.mirror_button.click()
    assert popup.isVisible()
    popup.home_button.click()
    spin(app, lambda: not popup.busy)
    source = workspace.plan.hardware_settings
    assert workspace._mirror_last_commanded == (source['home_x_voltage_v'], source['home_y_voltage_v'])


def test_popup_refuses_active_optical_lease(window):
    _, widget, workspace = window
    lease = workspace._ownership.reserve('Spectrum')
    try:
        widget.mirror_window.move()
        assert not widget.mirror_window.busy
        assert not hasattr(workspace, '_mirror_last_commanded')
    finally:
        lease.release()


def test_sequence_position_controls_visibility_settings_roundtrip(window, tmp_path):
    app, widget, _ = window
    panel = widget.pages['Sequences']
    widget.tabs.setCurrentWidget(panel)
    panel.spectrum_x.setValue(.25)
    panel.spectrum_y.setValue(-.35)
    panel.spectrum_settle.setValue(.002)
    assert panel.spectrum_position_card.isVisible()
    path = tmp_path / 'settings.json'
    widget.workspace_hub.export_settings(path)
    panel.spectrum_x.setValue(0)
    widget.workspace_hub.load_settings(path)
    assert panel.spectrum_x.value() == .25
    panel.measurement.setCurrentText('Intensity map')
    assert not panel.spectrum_position_card.isVisible()
    panel.measurement.setCurrentText('Spectrum')
    panel.save_output.setChecked(False)
    panel.start()
    spin(app, lambda: not panel.busy)
    assert panel.last_result['spectrum_position'] == (.25, -.35, .002)


def test_real_positioned_spectrum_one_thread_move_before_capture_and_home(tmp_path, monkeypatch):
    from labtools.config.anneal_workspace import InstrumentProfile
    from labtools.config.native_candidate import preflight_candidate
    from labtools.runtime.hardware_workspace import HardwareWorkspace
    from labtools.runtime.operator_spectrum import ensure_operator_spectrum
    from labtools.simulation.transport_fakes import (
        TransportTrace,
        map_factories,
        spectrum_factory,
    )

    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path/'program'))
    monkeypatch.delenv('LABTOOLS_INSTRUMENT_PROFILE', raising=False)
    shutil.copytree(ROOT/'examples/workspace/working-lab', tmp_path/'bundle')
    manifest = tmp_path/'bundle/candidate.json'
    profile = tmp_path/'profile.json'
    profile.write_text(json.dumps(asdict(InstrumentProfile(profile_id='test', approved=True))))
    plan = preflight_candidate(manifest).plan
    trace = TransportTrace()
    with HardwareWorkspace(manifest, anneal_profile=profile, preferences_path=tmp_path/'p.json',
        map_factories=map_factories(plan.map_config, trace),
        spectrometer_factory=spectrum_factory(plan.spectrum_request.settings, trace),
        stitcher=lambda captures, start, end: (np.array(captures[0][0]), np.array(captures[0][1][0]))) as workspace:
        ensure_operator_spectrum(workspace)
        batch = Batch(workspace._ownership, ('Spectrum', 'Intensity map'))
        try:
            with batch.borrow('Spectrum'), batch.borrow('Intensity map'):
                result = positioned_spectrum(workspace, workspace.workflows.spectrum_settings(), (.2, -.3, 0))
            assert result.intensity.size > 0
            events = trace.events()
            moves = [i for i,e in enumerate(events) if e['resource']=='mirror' and e['action']=='move']
            connections = [i for i,e in enumerate(events) if e['resource']=='spectrometer' and e['action']=='connect']
            assert len(moves)==2 and len(connections)==1 and moves[0] < connections[0] < moves[1]
            assert len({e['thread'] for e in events}) == 1
        finally:
            batch.release()


def test_cancel_during_settle_homes_and_skips_spectrum(workspace, monkeypatch):
    import time
    from threading import Thread

    from labtools.runtime.operator_spectrum import ensure_operator_spectrum
    runtime = ensure_operator_spectrum(workspace)
    stop = Event()
    def cancel():
        deadline = time.monotonic() + 3
        while not hasattr(workspace, '_mirror_last_commanded') and time.monotonic() < deadline:
            time.sleep(.001)
        stop.set()
    thread = Thread(target=cancel)
    batch = Batch(workspace._ownership, ('Spectrum', 'Intensity map'))
    try:
        thread.start()
        with batch.borrow('Spectrum'), batch.borrow('Intensity map'), pytest.raises(asyncio.CancelledError):
            positioned_spectrum(workspace, workspace.workflows.spectrum_settings(), (.2, .3, 5), stop=stop)
        source = workspace.plan.hardware_settings
        assert workspace._mirror_last_commanded == (source['home_x_voltage_v'], source['home_y_voltage_v'])
        assert runtime.worker.status().state == 'available'
    finally:
        thread.join(3)
        batch.release()


def test_global_stop_and_active_close_include_manual_command(window, monkeypatch):
    app, widget, workspace = window
    from labtools.gui import workspace_mirror_popup
    entered = Event()
    release = Event()
    def blocked(workspace, x, y, *, stop):
        entered.set()
        assert release.wait(3)
        return {'x_voltage_v': x, 'y_voltage_v': y}
    monkeypatch.setattr(workspace_mirror_popup, 'move_manual', blocked)
    widget.mirror_window.move()
    spin(app, entered.is_set)
    assert widget.any_busy()
    widget.stop_all()
    assert widget.mirror_window.stop_event.is_set()
    widget.close()
    assert not workspace._closed
    release.set()
    spin(app, lambda: workspace._closed)


def test_position_failure_aborts_before_baseline_or_anneal(workspace, monkeypatch):
    from labtools.runtime import workspace_mirror
    anneals = []
    monkeypatch.setattr(workspace, 'acquire_anneal', lambda *a, **k: anneals.append(True))
    def fail(*args, **kwargs):
        raise OSError('mirror target failed')
    monkeypatch.setattr(workspace_mirror, 'positioned_spectrum', fail)
    with pytest.raises(OSError, match='mirror target') as caught:
        run_sequence(workspace, program(workspace), 'Spectrum', workspace.workflows.spectrum_settings(),
            cycles=2, save_output=False, spectrum_position=(.1, .2, 0))
    assert not anneals
    assert caught.value.retained_run['status'] == 'failed'
    assert not caught.value.retained_run['steps']
    assert all(s.owner is None for s in workspace._ownership.status().resources)
