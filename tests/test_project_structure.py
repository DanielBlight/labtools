"""Offline regression checks for module boundaries and command routing."""
from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from labtools import cli, launchers
from labtools.processing.background import apply_background_subtraction, parse_background_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tool", tuple(launchers.GUI_MODULES))
def test_gui_dispatch_is_lazy(monkeypatch, tool):
    calls = []
    monkeypatch.setattr(launchers, "import_module", lambda name: SimpleNamespace(main=lambda: calls.append(name)))
    launchers.launch_gui(tool)
    assert calls == [launchers.GUI_MODULES[tool]]


def test_unknown_gui_does_not_import(monkeypatch):
    monkeypatch.setattr(launchers, "import_module", lambda name: pytest.fail(name))
    with pytest.raises(ValueError, match="Unknown GUI"):
        launchers.launch_gui("unknown")


@pytest.mark.parametrize("tool", tuple(launchers.GUI_MODULES))
def test_cli_gui_routing(monkeypatch, tool):
    calls = []
    monkeypatch.setattr(cli, "launch_gui", calls.append)
    cli.main(["gui", tool])
    assert calls == [tool]


def test_cli_rejects_unknown_arguments_before_launch(monkeypatch):
    monkeypatch.setattr(cli, "launch_gui", lambda tool: pytest.fail(tool))
    with pytest.raises(SystemExit) as exc:
        cli.main(["gui", "mirror", "--unexpected"])
    assert exc.value.code == 2


def test_simulation_arguments_forwarded(monkeypatch):
    from labtools.simulation import intensity_map
    calls = []
    monkeypatch.setattr(intensity_map, "main", lambda args: calls.append(args))
    cli.main(["simulate", "intensity-map", "--points", "3", "--seed", "4"])
    assert calls == [["--points", "3", "--seed", "4"]]


def test_compatibility_exports_are_same_objects():
    from labtools import operator_cli
    from labtools.acquisition.intensity_map import IntensityMapConfig as legacy_config
    from labtools.config.intensity_map import IntensityMapConfig
    from labtools.gui import background
    from labtools.runtime.map_devices import open_map_devices
    from labtools.simulation import map_backend
    assert operator_cli.main is cli.main
    assert legacy_config is IntensityMapConfig
    assert background.parse_background_csv is parse_background_csv
    assert map_backend.open_map_devices is open_map_devices


def test_help_and_configuration_import_without_native_dependencies(tmp_path):
    code = r''' 
import importlib.abc
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('PyQt6', 'labtools.devices', 'u6', 'pyvisa', 'serial', 'pylablib', 'pyft232')):
            raise AssertionError('Native import: ' + fullname)
sys.meta_path.insert(0, Block())
from labtools.cli import main
from labtools.config.intensity_map import IntensityMapConfig
from labtools.runtime.map_devices import open_map_devices
from labtools.processing.background import parse_background_csv
main(['--help'])
'''
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_background_csv_and_subtraction(tmp_path):
    path = tmp_path / "background.csv"
    path.write_text("wavelength,intensity\n500,2\n501,3\n")
    x, y = parse_background_csv(path)
    result = apply_background_subtraction(x, np.array([10., 20.]), (x, y))
    np.testing.assert_array_equal(result, [8., 17.])


@pytest.mark.parametrize("kind", ["missing", "mismatched"])
def test_background_rejects_invalid_axis(kind):
    x = np.array([500., 501.])
    background = None if kind == "missing" else (x + 1, np.ones(2))
    with pytest.raises(ValueError):
        apply_background_subtraction(x, np.ones(2), background)


@pytest.mark.parametrize("fail_controller", [False, True])
def test_real_factory_cleanup_with_fake_devices(monkeypatch, fail_controller):
    from labtools.runtime.map_devices import open_map_devices
    events = []
    class Resource:
        def __init__(self, name): self.name = name
        def __enter__(self):
            events.append("enter:" + self.name)
            if self.name == "controller" and fail_controller:
                raise RuntimeError("injected open failure")
            return self
        def __exit__(self, *args): events.append("exit:" + self.name)
    replacements = {
        "labtools.devices.labjack_u6": ("LabJackU6", lambda: Resource("labjack")),
        "labtools.devices.idq_time_controller": ("IDQTimeController", lambda address: Resource("controller")),
        "labtools.devices.scanning_mirror": ("ScanningMirror", lambda device, **kwargs: object()),
        "labtools.devices.spad_gate": ("SPADGate", lambda device, **kwargs: object()),
    }
    importlib.import_module("labtools.devices")
    for name, (symbol, value) in replacements.items():
        module = ModuleType(name)
        setattr(module, symbol, value)
        monkeypatch.setitem(sys.modules, name, module)
    config = SimpleNamespace(backend="real", time_controller_address="unused", mirror_dio_pin=2, spad_gate_pin=0)
    if fail_controller:
        with pytest.raises(RuntimeError, match="injected"):
            with open_map_devices(config):
                pytest.fail("must not yield")
        assert events == ["enter:labjack", "enter:controller", "exit:labjack"]
    else:
        with open_map_devices(config) as devices:
            assert len(devices) == 3
        assert events == ["enter:labjack", "enter:controller", "exit:controller", "exit:labjack"]


def test_hardware_modules_excluded_before_import():
    tree = ast.parse((ROOT / "tests/conftest.py").read_text())
    hook = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "pytest_ignore_collect")
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[hook], type_ignores=[])), "hook", "exec"), namespace)
    for enabled in (False, True):
        config = SimpleNamespace(getoption=lambda name: enabled)
        result = namespace["pytest_ignore_collect"](Path("test_sc10_modes.py"), config)
        assert result is (None if enabled else True)


def test_console_entry_points_resolve_without_gui_imports():
    import tomllib
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]
    for target in scripts.values():
        module, name = target.split(":")
        assert callable(getattr(importlib.import_module(module), name))
