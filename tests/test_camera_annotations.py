"""Overlay coordinates/undo and explicit synthetic source, without native imports."""

import builtins
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import numpy as np
import pytest

from labtools.processing.camera_annotations import CameraAnnotations, image_point
from labtools.simulation.camera import SimulatedCamera, SimulatedIllumination


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in
               ("labtools.devices", "pylablib", "u6", "serial", "pyvisa", "horiba_sdk")):
            raise AssertionError("Synthetic preview attempted native import: " + name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_raw_coordinate_mapping_letterbox_and_resize():
    assert image_point(500, 400, (100, 100, 800, 600), (640, 480)) == (320, 240)
    assert image_point(250, 200, (50, 50, 400, 300), (640, 480)) == (320, 240)
    assert image_point(0, 0, (100, 100, 800, 600), (640, 480)) is None
    assert image_point(1, 1, (0, 0, 0, 0), (640, 480)) is None
    assert image_point(1, 1, (0, 0, 2, 2), None) is None


def test_circle_labels_radius_undo_and_clear_undo():
    model = CameraAnnotations()
    model.set_geometry(640, 480)
    first = model.add((100, 100), (103, 104), "  spot A\nreference ")
    assert first.radius == 5 and first.label == "spot A reference"
    second = model.add((200, 200), (210, 200))
    assert second.label == "Circle 2"
    assert model.undo() and model.circles == [first]
    model.add((200, 200), (210, 200), "B")
    model.clear()
    assert not model.circles and model.can_undo
    assert model.undo() and len(model.circles) == 2
    model.undo()
    model.undo()
    assert not model.circles and not model.undo()


def test_geometry_change_clears_not_resizes_and_same_geometry_retains():
    model = CameraAnnotations()
    model.set_geometry(640, 480)
    model.add((100, 100), (110, 100))
    assert not model.set_geometry(640, 480) and len(model.circles) == 1
    assert model.set_geometry(1280, 960) and not model.circles and not model.can_undo


@pytest.mark.parametrize("centre,edge", [((-1, 0), (2, 3)), ((0, 0), (641, 0)), ((1, 1), (1, 1)),
                                       ((float("nan"), 1), (2, 3)), ((1, 1), (float("inf"), 2))])
def test_invalid_annotations_do_not_change_history(centre, edge):
    model = CameraAnnotations()
    model.set_geometry(640, 480)
    with pytest.raises(ValueError):
        model.add(centre, edge)
    assert not model.circles and not model.can_undo


@pytest.mark.parametrize("spacing,count", [(0, 3), (float("nan"), 3), (50, 0), (50, 21), (50, True)])
def test_invalid_ring_controls(spacing, count):
    with pytest.raises(ValueError):
        CameraAnnotations().configure(crosshair=True, rings=True, spacing=spacing, count=count)


def test_annotation_limits_and_text_bound():
    model = CameraAnnotations()
    model.set_geometry(640, 480)
    for _ in range(200):
        model.add((10, 10), (20, 10), "x" * 100)
    assert len(model.circles[-1].label) == 80
    with pytest.raises(ValueError, match="200"):
        model.add((10, 10), (20, 10))
    assert len(model._history) == 200


def test_synthetic_raw_dtype_movement_exposure_gain_and_dark():
    light = SimulatedIllumination()
    with SimulatedCamera(illumination=light) as camera:
        assert "SIMULATED" in camera.get_device_info()
        camera.start_live()
        bright = camera.read_latest()
        light.set_dark(True)
        dark = camera.read_latest()
        assert bright.shape == (480, 640) and bright.dtype == np.uint8
        assert bright.max() > dark.max() + 80
        assert bright.mean() > dark.mean()
        camera.set_master_gain(2)
        higher_dark = camera.read_latest()
        assert higher_dark.mean() > dark.mean()
        light.set_dark(False)
        camera.set_exposure(.04)
        assert camera.get_exposure() == .04
        assert camera.read_latest().max() >= bright.max()
    with pytest.raises(RuntimeError, match="lifetime"):
        camera.read_latest()


def test_synthetic_repeatability_and_no_native_identity():
    first = SimulatedCamera(seed=5)
    second = SimulatedCamera(seed=5)
    try:
        first.start_live()
        second.start_live()
        assert np.array_equal(first.read_latest(), second.read_latest())
        assert "no physical device" in first.get_device_info()
    finally:
        first.close()
        second.close()


def test_synthetic_thread_affinity_and_stop_wait():
    stop = Event()
    with SimulatedCamera(stop_event=stop) as camera:
        camera.start_live()
        with (
            ThreadPoolExecutor(max_workers=1) as executor,
            pytest.raises(RuntimeError, match="thread"),
        ):
            executor.submit(camera.get_exposure).result()
        camera.read_latest()
        stop.set()
        assert not camera.read_latest().any()


@pytest.mark.parametrize("exposure", [0, -1, float("nan"), 11])
def test_invalid_synthetic_exposure(exposure):
    with pytest.raises(ValueError):
        SimulatedCamera(exposure_s=exposure)
