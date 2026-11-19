"""Actual unified synthetic GUI: existing workers, camera and cooperative cleanup."""

import builtins
import shutil
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_simulated_workspace_all_workflows_and_camera(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError as error:
        pytest.skip(f"Unified simulation Qt acceptance unavailable: {error}")
    from labtools.gui.native_workspace import create_window
    from labtools.simulation.operator_session import SimulatedOperatorSession

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "pylablib", "u6", "serial", "pyvisa")):
            raise AssertionError("Synthetic operator UI attempted native import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest = tmp_path / "bundle/candidate.json"
    before = {path: path.read_bytes() for path in manifest.parent.iterdir()}
    app = QApplication.instance() or QApplication([])

    def wait(predicate):
        end = time.monotonic() + 20
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic() < end, "Synthetic worker cleanup timed out"
        app.processEvents()

    with SimulatedOperatorSession(manifest, output_root=tmp_path / "synthetic", realtime=True) as session:
        window = create_window(session)
        mapping, spectrum, anneal = (window.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
        try:
            window.show()
            app.processEvents()
            assert window.tabs.count() == 4 and "SIMULATION" in window.windowTitle()
            assert mapping.simulation_mode.isChecked() and not mapping.simulation_mode.isEnabled()
            assert window.camera_window.source.count() == 1
            window.open_camera()
            window.camera_window.start_button.click()
            wait(lambda: window.camera_window._last_packet is not None)
            assert not session._ownership.session.reservations()  # Synthetic camera is independent.
            mapping.x_points.setValue(3)
            mapping.y_points.setValue(2)
            mapping.integration.setValue(.01)
            mapping.settle.setValue(0)
            mapping.save_results.setChecked(False)
            errors = []
            mapping.map_controller.failed.connect(lambda *args: errors.append(args))
            mapping._start_worker(mapping._config())
            wait(lambda: not mapping.map_controller.busy)
            assert not errors and mapping._workspace_lease is None
            assert not session._ownership.session.reservations()
            results, spectrum_errors = [], []
            spectrum_settings = spectrum._snapshot_settings()
            spectrum._start_operation(
                lambda: session.acquire_spectrum(spectrum_settings),
                results.append, spectrum_errors.append, "SIMULATED test spectrum",
            )
            wait(lambda: not spectrum._async_tasks)
            assert len(results) == 1 and not spectrum_errors
            assert results[0].settings.backend == "simulation" and spectrum._workspace_lease is None
            anneal.x_points.setValue(2)
            anneal.y_points.setValue(2)
            anneal.dwell.setValue(.01)
            anneal.save_log.setChecked(False)
            anneal.start_button.click()
            wait(lambda: anneal._thread is None)
            assert session.anneal_simulator.snapshot()["completed_points"] == 4
            assert session.anneal_simulator.snapshot()["shutter"] == "closed"
            assert anneal._workspace_lease is None
            # Long synthetic run exercises Stop all and deferred window close.
            anneal.x_points.setValue(20)
            anneal.y_points.setValue(20)
            anneal.dwell.setValue(.02)
            anneal.start_button.click()
            wait(lambda: session.anneal_simulator.snapshot()["running"])
            window.close()
            assert not session._closed
            wait(lambda: not window.any_busy())
            assert session.anneal_simulator.snapshot()["shutter"] == "closed"
            assert not session._ownership.session.reservations()
            assert window.save_preferences()
        finally:
            window.stop_all()
            wait(lambda: not window.any_busy())
            window.close()
            app.processEvents()
        assert session._closed
    with SimulatedOperatorSession(manifest) as session:
        assert session.drafts.values["map"].x_points == 3
        assert session.drafts.values["anneal"].x_points == 20
        assert session.drafts.values["map"].backend == "simulation"
    assert all(path.read_bytes() == data for path, data in before.items())
