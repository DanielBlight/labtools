"""Simulation GUI launcher contracts without importing Qt or devices."""

import sys
from types import ModuleType

import pytest

from labtools.simulation.intensity_map import main


@pytest.fixture
def fake_gui(monkeypatch):
    created = []

    class Field:
        def __init__(self, value):
            self.value = value

        def setValue(self, value):
            self.value = value

        def setText(self, value):
            self.value = value

    class Window:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.x_points = Field(23)
            self.y_points = Field(24)
            self.output_root = Field("remembered-output")
            created.append(self)

        def show(self):
            self.shown = True

    class App:
        def __init__(self, args):
            pass

        def setFont(self, font):
            pass

        def exec(self):
            return 0

    qt = ModuleType("PyQt6")
    qt.__path__ = []
    gui = ModuleType("PyQt6.QtGui")
    gui.QFont = lambda *args: None
    widgets = ModuleType("PyQt6.QtWidgets")
    widgets.QApplication = App
    window_module = ModuleType("labtools.gui.intensity_map_gui")
    window_module.IntensityMapWindow = Window
    for name, module in {
        "PyQt6": qt, "PyQt6.QtGui": gui, "PyQt6.QtWidgets": widgets,
        "labtools.gui.intensity_map_gui": window_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return created


def test_gui_preserves_remembered_settings_without_overrides(fake_gui):
    with pytest.raises(SystemExit) as caught:
        main(["--gui"])
    assert caught.value.code == 0
    window = fake_gui[0]
    assert window.kwargs == {
        "simulation_only": True, "simulation_seed": 0, "simulation_realtime": False,
    }
    assert (window.x_points.value, window.y_points.value) == (23, 24)
    assert window.output_root.value == "remembered-output"
    assert window.shown


def test_gui_honours_explicit_seed_timing_points_and_output(fake_gui, tmp_path):
    with pytest.raises(SystemExit):
        main(["--gui", "--seed", "42", "--realtime", "--points", "5", "--output", str(tmp_path)])
    window = fake_gui[0]
    assert window.kwargs["simulation_seed"] == 42
    assert window.kwargs["simulation_realtime"] is True
    assert (window.x_points.value, window.y_points.value) == (5, 5)
    assert window.output_root.value == str(tmp_path)


@pytest.mark.parametrize("args", [["--resume", "folder"], ["--stop-after", "2"]])
def test_gui_rejects_silently_ignored_cli_operations(fake_gui, args):
    with pytest.raises(SystemExit) as caught:
        main(["--gui", *args])
    assert caught.value.code == 2
    assert not fake_gui


@pytest.mark.parametrize("args", [["--points", "1"], ["--seed", "-1"]])
def test_invalid_options_fail_before_gui(fake_gui, args):
    with pytest.raises(SystemExit) as caught:
        main(["--gui", *args])
    assert caught.value.code == 2
    assert not fake_gui
