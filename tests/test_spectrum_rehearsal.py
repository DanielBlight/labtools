"""Synthetic workflow rehearsal, exports and refusal boundaries."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples/measurements/rehearse_spectrum.py"
RECIPE = ROOT / "examples/measurements/recipes/spectrum_simulation.json"


@pytest.fixture
def rehearsal():
    spec = importlib.util.spec_from_file_location("isolated_spectrum_rehearsal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_complete_workflow_exports_reopens_and_repeats(rehearsal, tmp_path):
    first = rehearsal.rehearse(RECIPE, tmp_path)
    second = rehearsal.rehearse(RECIPE, tmp_path)
    assert first["status"] == second["status"] == "passed"
    assert first["points"] == 64
    assert len(first["checks"]) == 7 and all(first["checks"].values())
    assert first["output_directory"] != second["output_directory"]
    folder = Path(first["output_directory"])
    assert folder.parent.name == "SIMULATION"
    assert (folder / "SYNTHETIC_DATA.txt").is_file()
    assert (folder / "spectrum.png").stat().st_size > 0
    lines = (folder / "spectrum.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# SYNTHETIC")
    assert len(lines) == 66
    with np.load(folder / "corrected_spectrum.npz", allow_pickle=False) as data:
        metadata = json.loads(str(data["metadata"].item()))
        assert metadata["synthetic_data"]
        assert metadata["dark_mode"] == "pre_taken"
    assert json.loads((folder / "rehearsal.json").read_text(encoding="utf-8")) == first


@pytest.mark.parametrize("kind,backend", [("spectrum", "real"), ("alignment", "simulation")])
def test_refuses_wrong_kind_or_real_backend_before_runtime(rehearsal, tmp_path, monkeypatch, kind, backend):
    from types import SimpleNamespace

    monkeypatch.setattr(rehearsal, "load_recipe", lambda path: SimpleNamespace(kind=kind, backend=backend))
    monkeypatch.setattr(rehearsal, "SpectrumRuntime", lambda **kwargs: pytest.fail("Runtime must not be created"))
    with pytest.raises(ValueError, match="real execution is refused"):
        rehearsal.rehearse(RECIPE, tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()


def test_refuses_pre_subtracted_recipe(rehearsal, tmp_path):
    data = json.loads(RECIPE.read_text(encoding="utf-8"))
    data["recipe"]["dark_mode"] = "per_center"
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="dark_mode='none'"):
        rehearsal.rehearse(recipe, tmp_path / "outputs")
    assert not (tmp_path / "outputs").exists()


def test_export_failure_retains_failed_report_and_existing_data(rehearsal, tmp_path, monkeypatch):
    def fail_export(*args):
        raise OSError("export failed")

    monkeypatch.setattr(rehearsal, "save_spectrum_result", fail_export)
    with pytest.raises(OSError, match="export failed"):
        rehearsal.rehearse(RECIPE, tmp_path)
    folder = next((tmp_path / "SIMULATION").iterdir())
    report = json.loads((folder / "rehearsal.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["error"] == "OSError: export failed"
    assert (folder / "dark.npz").exists()
    assert (folder / "SYNTHETIC_DATA.txt").exists()


def test_allocation_collision_preserves_previous_folder(rehearsal, tmp_path, monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            from datetime import datetime

            return datetime(2026, 11, 18, 12, 0, tzinfo=tz)

    monkeypatch.setattr(rehearsal, "datetime", Clock)
    first = rehearsal._allocate(tmp_path)
    marker = first / "existing.txt"
    marker.write_text("keep", encoding="utf-8")
    second = rehearsal._allocate(tmp_path)
    assert second.name == first.name + "-001"
    assert marker.read_text(encoding="utf-8") == "keep"


def test_cli_failure_is_actionable(rehearsal, tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        rehearsal.main(["--recipe", str(tmp_path / "missing.json"), "--output", str(tmp_path / "outputs")])
    assert caught.value.code == 1
    assert "Rehearsal failed" in capsys.readouterr().err


def test_full_cli_rehearsal_forbids_native_and_qt_imports(tmp_path):
    code = r'''
import builtins, runpy, sys
original = builtins.__import__
blocked = ("PyQt6", "u6", "pyvisa", "serial", "horiba_sdk", "labtools.devices", "labtools.gui")
def guarded(name, *args, **kwargs):
    if any(name == prefix or name.startswith(prefix + ".") for prefix in blocked):
        raise AssertionError("Forbidden import: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = [sys.argv[1], "--recipe", sys.argv[2], "--output", sys.argv[3]]
runpy.run_path(sys.argv[0], run_name="__main__")
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), MPLBACKEND="Agg")
    result = subprocess.run(
        [sys.executable, "-c", code, str(SCRIPT), str(RECIPE), str(tmp_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC SPECTROSCOPY REHEARSAL PASSED" in result.stdout
