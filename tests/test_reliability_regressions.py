"""Focused real-method tests with fake devices; no hardware or Qt imports.

AST extraction deliberately isolates logic from native imports. These tests
are not a substitute for full application and hardware integration testing.
"""

import ast
import copy
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_method(relative, class_name, method_name, **extra):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8-sig"))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    )
    method = copy.deepcopy(
        next(
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == method_name
        )
    )
    method.decorator_list = []
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[future, method], type_ignores=[])
    )
    namespace = {"np": np, "re": re, "__name__": __name__}
    namespace.update(extra)
    exec(compile(module, relative, "exec"), namespace)
    return namespace[method_name]


@pytest.mark.parametrize(
    "stop_error,close_error",
    [(False, False), (True, False), (False, True), (True, True)],
)
def test_camera_cleanup(stop_error, close_error):
    close = load_method(
        "src/labtools/devices/uc480_camera.py",
        "ThorlabsUC480Camera",
        "close",
        UC480CameraError=RuntimeError,
    )
    device = Mock()
    if stop_error:
        device.stop_acquisition.side_effect = OSError("stop failed")
    if close_error:
        device.close.side_effect = OSError("close failed")
    wrapper = SimpleNamespace(_camera=device, _live=True)
    if stop_error or close_error:
        with pytest.raises(RuntimeError) as error:
            close(wrapper)
        assert len(error.value.__cause__.exceptions) == int(stop_error) + int(
            close_error
        )
    else:
        close(wrapper)
    device.stop_acquisition.assert_called_once()
    device.close.assert_called_once()
    assert wrapper._camera is None and not wrapper._live
    close(wrapper)
    device.close.assert_called_once()


@pytest.mark.parametrize("mirror", [False, True])
def test_owned_camera_frame(mirror):
    prepare = load_method(
        "src/labtools/devices/uc480_camera.py",
        "ThorlabsUC480Camera",
        "_prepare_frame",
        UC480CameraError=RuntimeError,
    )
    source = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    expected = source[:, ::-1].copy() if mirror else source.copy()
    result = prepare(SimpleNamespace(mirror_horizontal=mirror), source)
    source[:] = 0
    np.testing.assert_array_equal(result, expected)
    assert result.flags.c_contiguous


@pytest.mark.parametrize("response", [b" closed?\r\n1\r\n> ", b"closed?\r1\r> "])
def test_sc10_echo(response):
    exchange = load_method("src/labtools/devices/sc10.py", "SC10", "_exchange")
    connection = Mock()
    connection.read_until.return_value = response
    wrapper = SimpleNamespace(_connection=lambda: connection)
    assert exchange(wrapper, "closed?") == ["1"]
    connection.write.assert_called_once_with(b"closed?\r")


def test_diagnostic_constructor_matches_wrapper():
    source = (ROOT / "scripts/camera/check_uc480_camera.py").read_text()
    calls = [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "ThorlabsUC480Camera"
    ]
    assert len(calls) == 1
    assert [k.arg for k in calls[0].keywords] == ["exposure_s"]


@pytest.mark.parametrize("enabled", [False, True])
def test_hardware_opt_in(enabled):
    tree = ast.parse((ROOT / "tests/conftest.py").read_text(encoding="utf-8-sig"))
    hook = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "pytest_collection_modifyitems"
    )
    namespace = {"pytest": pytest}
    module = ast.fix_missing_locations(ast.Module(body=[hook], type_ignores=[]))
    exec(compile(module, "conftest", "exec"), namespace)
    markers = []
    item = SimpleNamespace(path=Path("test_timestamp_stream.py"), fixturenames=[])
    item.add_marker = markers.append
    item.get_closest_marker = lambda name: next(
        (m for m in markers if m.name == name), None
    )
    config = SimpleNamespace(getoption=lambda name: enabled)
    namespace["pytest_collection_modifyitems"](config, [item])
    assert item.get_closest_marker("hardware") is not None
    assert (item.get_closest_marker("skip") is None) == enabled
