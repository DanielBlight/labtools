"""Actual native panel/worker binding. Missing Qt is a skip, never acceptance."""

import builtins
import json
import shutil
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_operator_panels_preview_refuse_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    try:
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError as error:
        pytest.skip(f"Actual native workflow Qt acceptance unavailable: {error}")
    from labtools.gui.native_workspace import create_window
    from labtools.runtime.native_workspace import NativeWorkspace

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa")):
            raise AssertionError("Native import during gated operator binding: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "exec", lambda *args: QMessageBox.StandardButton.Ok)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest = tmp_path / "bundle/candidate.json"
    before = {path: path.read_bytes() for path in manifest.parent.iterdir()}
    # Verify native drafts do not read or overwrite the standalone map preferences.
    preferences = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    preferences.setValue("preferences_v1/x_points", 99)
    preferences.sync()
    settings_before = (tmp_path / "preferences.ini").read_bytes()
    import PyQt6.QtCore as core

    monkeypatch.setattr(core, "QSettings", lambda *args, **kwargs: preferences)
    app = QApplication.instance() or QApplication([])

    def wait(predicate):
        end = time.monotonic() + 15
        while not predicate():
            app.processEvents()
            time.sleep(.005)
            assert time.monotonic() < end, "Gated worker did not finish cleanup"
        app.processEvents()

    with NativeWorkspace(manifest) as workspace:
        window = create_window(workspace)
        mapping, spectrum = window.pages["Intensity map"], window.pages["Spectrum"]
        try:
            window.show()
            app.processEvents()
            assert window.tabs.count() == 5
            assert mapping._config() == workspace.plan.map_config
            assert spectrum._snapshot_settings() == workspace.plan.spectrum_request.settings
            assert mapping.map_controller._acquisition.__self__ is workspace
            assert spectrum._service is workspace.spectrum_service
            assert mapping._ownership is spectrum._ownership is workspace._ownership
            assert not mapping.simulation_mode.isChecked() and not mapping.simulation_mode.isEnabled()
            assert mapping.address.isReadOnly()
            assert all(not button.isEnabled() for button in window.operation_buttons)
            assert mapping.laser_light.text() == spectrum.laser_light.text() == "Laser state: NOT PROBED"
            mapping.x_points.setValue(7)
            mapping.y_points.setValue(8)
            spectrum.preset_combo.setCurrentText("symphony")
            spectrum.exposure_box.setValue(.1)
            window.preview_button.click()
            draft = json.loads(window.report.toPlainText())["operator_draft"]
            assert draft["map"]["x_points"] == 7 and draft["spectrum"]["preset"] == "symphony"
            assert draft["detector_expectations_not_readbacks"]["expected_serial_number"] == "Camera SN: 26070"
            assert draft["draft_only"] and not draft["execution_enabled"]
            for operation in (mapping.start_new, mapping.choose_resume, mapping.connect_laser,
                              spectrum.acquire_spectrum, spectrum.capture_reusable_dark,
                              spectrum.test_spectrometer_connection, spectrum.connect_laser):
                operation()
            assert not mapping.map_controller.busy and not spectrum._async_tasks
            assert not workspace._ownership.session.reservations()
            # Exercise the already-bound real worker classes with the refusing service.
            # This bypasses only the disabled UI entry point, never the runtime gate.
            map_errors = []
            mapping.map_controller.failed.connect(lambda *args: map_errors.append(args))
            for _ in range(2):
                mapping._workspace_lease = workspace._ownership.reserve("Intensity map")
                mapping.map_controller.start(mapping._config())
                wait(lambda: not mapping.map_controller.busy)
                assert mapping._workspace_lease is None
                assert not workspace._ownership.session.reservations()
            assert len(map_errors) == 2 and all("disabled" in item[0].lower() for item in map_errors)
            errors = []
            spectrum_settings = spectrum._snapshot_settings()
            for _ in range(2):
                spectrum._workspace_lease = workspace._ownership.reserve("Spectrum")
                spectrum._run_async(
                    lambda: workspace.acquire_spectrum(spectrum_settings),
                    lambda result: pytest.fail("Gated spectrum unexpectedly succeeded"), errors.append,
                )
                wait(lambda: not spectrum._async_tasks)
                assert spectrum._workspace_lease is None
                assert not workspace._ownership.session.reservations()
            assert len(errors) == 2 and all("disabled" in error.lower() for error in errors)
            assert all(not button.isEnabled() for button in window.operation_buttons)
            assert all(path.read_bytes() == data for path, data in before.items())
        finally:
            if mapping.map_controller.busy:
                mapping.map_controller.cancel()
                wait(lambda: not mapping.map_controller.busy)
            if spectrum._async_tasks:
                spectrum.request_stop()
                wait(lambda: not spectrum._async_tasks)
            window.close()
            app.processEvents()
        assert workspace._closed
    assert (tmp_path / "preferences.ini").read_bytes() == settings_before
