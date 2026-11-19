"""Actual Qt window smoke test; a missing Qt runtime is a skip, never acceptance."""

import builtins
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_native_window_is_disabled_refreshes_and_closes(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program"))
    monkeypatch.delenv("LABTOOLS_INSTRUMENT_PROFILE", raising=False)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError as error:
        pytest.skip(f"Actual Qt window acceptance unavailable: {error}")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    from labtools.gui.native_workspace import create_window
    from labtools.runtime.native_workspace import NativeWorkspace

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "horiba_sdk", "u6", "serial", "pyvisa")):
            raise AssertionError("Native import in read-only Qt workspace: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    shutil.copytree(ROOT / "examples/workspace/working-lab", tmp_path / "bundle")
    manifest = tmp_path / "bundle/candidate.json"
    app = QApplication.instance() or QApplication([])
    with NativeWorkspace(manifest) as workspace:
        window = create_window(workspace)
        try:
            window.show()
            app.processEvents()
            assert all(not button.isEnabled() for button in window.operation_buttons)
            assert '"execution_enabled": false' in window.report.toPlainText()
            window.refresh_button.click()
            assert '"physical_serial": null' in window.report.toPlainText()
            manifest.write_text("{}")
            window.refresh_button.click()
            assert "Source status invalid" in window.report.toPlainText()
            assert all(not button.isEnabled() for button in window.operation_buttons)
        finally:
            window.close()
            app.processEvents()
        assert workspace._closed
