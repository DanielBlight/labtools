"""Actual four-tab UI, persistent settings and existing anneal worker gate."""

import builtins
import shutil
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_three_workflow_window_roundtrip_and_anneal_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError as error:
        pytest.skip(f"Unified Qt acceptance unavailable: {error}")
    from labtools.gui.native_workspace import create_window
    from labtools.runtime.native_workspace import NativeWorkspace

    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa")):
            raise AssertionError("Native import during unified candidate: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest, prefs = tmp_path / "bundle/candidate.json", tmp_path / "preferences.json"
    before = {path: path.read_bytes() for path in manifest.parent.iterdir()}
    app = QApplication.instance() or QApplication([])

    def wait(predicate):
        end = time.monotonic() + 15
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic() < end, "Worker cleanup timed out"
        app.processEvents()

    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        window = create_window(workspace)
        try:
            window.show()
            app.processEvents()
            assert window.tabs.count() == 4
            mapping, spectrum, anneal = (window.pages[name] for name in ("Intensity map", "Spectrum", "Annealing"))
            mapping.x_points.setValue(13)
            spectrum.exposure_box.setValue(.7)
            anneal.passes.setValue(3)
            anneal.dwell.setValue(.002)
            mapping.log_colour_scale.setChecked(True)
            window.preview_button.click()
            assert '"anneal_execution_enabled": false' in window.report.toPlainText()
            assert window.save_preferences()
            assert all(not button.isEnabled() for button in window.operation_buttons)
            for operation in (anneal._start, anneal._test_sc10, anneal._move_stage_to_anneal,
                              anneal._test_rotation_stage, anneal._start_camera):
                operation()
            assert anneal._thread is None and anneal._camera_thread is None
            # Existing AnnealWorker receives the gated acquisition callable. It
            # refuses before device imports, then releases the shared lease at idle.
            for _ in range(2):
                anneal._start_worker(anneal._build_config())
                wait(lambda: anneal._thread is None)
                assert anneal._workspace_lease is None
                assert not workspace._ownership.session.reservations()
                assert anneal.shutter_state.text() == "Shutter: NOT PROBED"
            assert not window.any_busy()
        finally:
            window.stop_all()
            wait(lambda: not window.any_busy())
            window.close()
            app.processEvents()
        assert workspace._closed
    with NativeWorkspace(manifest, preferences_path=prefs) as workspace:
        window = create_window(workspace)
        try:
            assert window.pages["Intensity map"].x_points.value() == 13
            assert window.pages["Spectrum"].exposure_box.value() == .7
            assert window.pages["Annealing"].passes.value() == 3
            assert window.pages["Intensity map"].log_colour_scale.isChecked()
            assert not window.pages["Annealing"].confirm.isChecked()
            assert not workspace._ownership.session.reservations()
            assert all(not button.isEnabled() for button in window.operation_buttons)
        finally:
            window.close()
            app.processEvents()
    assert all(path.read_bytes() == data for path, data in before.items())
