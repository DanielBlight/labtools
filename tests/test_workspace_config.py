"""Explicit resource configuration and service injection; no native/Qt imports."""

import importlib.util
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from labtools.config.workspace import WorkspaceConfig, load_workspace_config
from labtools.runtime.session import ResourceBusyError
from labtools.simulation.ownership import WorkspaceOwnership

ROOT = Path(__file__).resolve().parents[1]


def test_config_roundtrip(tmp_path):
    config = WorkspaceConfig(simulation_seed=42)
    data = {"schema_version": 1, **asdict(config)}
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_workspace_config(path) == config


@pytest.mark.parametrize("change", [
    {"backend": "real"}, {"configuration_id": ""}, {"resources": ()},
    {"resources": ("path", "path")}, {"map_resources": ("missing",)},
    {"simulation_seed": True}, {"simulation_seed": -1}, {"simulation_realtime": 1},
])
def test_invalid_config_refused_before_session(change):
    with pytest.raises(ValueError):
        WorkspaceOwnership(replace(WorkspaceConfig(), **change))


@pytest.mark.parametrize("text", ['{}', '[]', '{"schema_version":1,"schema_version":1}', '{broken'])
def test_invalid_json_schema_rejected(tmp_path, text):
    path = tmp_path / "workspace.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_workspace_config(path)


def test_disjoint_resources_can_reserve_concurrently_without_devices():
    config = WorkspaceConfig(resources=("map", "spectrum"), map_resources=("map",), spectrum_resources=("spectrum",))
    ownership = WorkspaceOwnership(config)
    try:
        with ownership.reserve("Intensity map"), ownership.reserve("Spectrum"):
            assert len(ownership.session.reservations()) == 2
            assert not any(resource.connected for resource in ownership.status().resources)
            with pytest.raises(ResourceBusyError):
                ownership.reserve("Intensity map")
    finally:
        ownership.close()


def test_unknown_owner_does_not_create_lease():
    ownership = WorkspaceOwnership()
    try:
        with pytest.raises(ValueError):
            ownership.reserve("unknown")
        assert not ownership.session.reservations()
    finally:
        ownership.close()


def test_injected_services_reach_existing_panel_constructors(monkeypatch):
    captured = []

    class Base:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.map_controller = SimpleNamespace(idle=SimpleNamespace(connect=lambda callback: None))

    map_module = ModuleType("labtools.gui.intensity_map_gui")
    map_module.IntensityMapWindow = Base
    spectrum_module = ModuleType("labtools.gui.spectrum_gui_horiba")
    spectrum_module.HoribaRangeWindow = Base
    monkeypatch.setitem(sys.modules, "labtools.gui.intensity_map_gui", map_module)
    monkeypatch.setitem(sys.modules, "labtools.gui.spectrum_gui_horiba", spectrum_module)
    spec = importlib.util.spec_from_file_location("isolated_workspace_panels", ROOT / "src/labtools/gui/workspace_panels.py")
    panels = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panels)
    config = WorkspaceConfig(configuration_id="configured-toy", simulation_seed=42, simulation_realtime=False)
    ownership = WorkspaceOwnership(config)
    def acquisition(*args):
        return None
    service = object()
    try:
        panels.OwnedMapPanel(ownership=ownership, acquisition=acquisition)
        panels.OwnedSpectrumPanel(ownership=ownership, service=service)
        assert captured[0] == {
            "acquisition": acquisition, "simulation_only": True,
            "simulation_seed": 42, "simulation_realtime": False,
        }
        assert captured[1] == {"service": service, "backend": "simulation", "configuration_id": "configured-toy"}
    finally:
        ownership.close()


def test_real_config_cli_rejected_before_qt(tmp_path):
    from labtools.simulation.workspace import main

    data = {"schema_version": 1, **asdict(WorkspaceConfig(backend="real"))}
    path = tmp_path / "real.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        main(["--config", str(path)])
    assert caught.value.code == 2
