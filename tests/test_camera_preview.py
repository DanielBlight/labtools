"""Raw dark arithmetic, bounded display, imports and camera worker affinity offline."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event, get_ident

import numpy as np
import pytest

from labtools.io.camera_dark import load_numeric_dark, save_dark_archive
from labtools.processing.camera_preview import (
    CameraContext,
    LatestPreview,
    PreviewProcessor,
    raw_frame,
)
from labtools.runtime.camera_stream import CameraTargets, pump_camera

CTX = CameraContext(.02, 1., "test-only camera")


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
@pytest.mark.parametrize("shape", [(6, 8), (6, 8, 3), (6, 8, 4)])
def test_capture_raw_subtract_signed_clip_and_no_input_mutation(dtype, shape):
    processor = PreviewProcessor()
    raw = np.full(shape, 20, dtype=dtype)
    processor.capture_dark()
    processor.process(raw, CTX)
    raw[...] = 10
    processor.enable(True)
    result = processor.process(raw, CTX)
    assert result.corrected
    assert not result.pixels.any()  # No unsigned underflow.
    dark, context, origin = processor.dark_snapshot()
    assert (dark == 20).all() and context == CTX and origin == "captured raw frame"
    assert (raw == 10).all()
    assert result.pixels.flags.c_contiguous and not result.pixels.flags.writeable


def test_subtraction_before_scaling_and_full_resolution_dark():
    processor = PreviewProcessor()
    processor.set_size(4, 3)
    dark = np.full((12, 16), 512, np.uint16)
    processor.load_dark(dark, context=CTX)
    processor.enable(True)
    result = processor.process(np.full((12, 16), 1536, np.uint16), CTX)
    assert result.pixels.shape == (3, 4)
    assert (result.pixels == (1024 * 255 // 65535)).all()
    assert processor.dark_snapshot()[0].shape == (12, 16)
    processor.set_white(4095)
    assert (processor.process(np.full((12, 16), 1536, np.uint16), CTX).pixels == 63).all()


@pytest.mark.parametrize("other", [replace(CTX, exposure_s=.03), replace(CTX, gain=2), replace(CTX, device="other")])
def test_dark_settings_or_identity_mismatch_is_visible_bypass(other):
    processor = PreviewProcessor()
    processor.load_dark(np.ones((2, 3), np.uint8), context=CTX)
    processor.enable(True)
    result = processor.process(np.full((2, 3), 10, np.uint8), other)
    assert not result.corrected and "changed" in result.dark_status
    assert (result.pixels == 10).all()


@pytest.mark.parametrize("dark", [np.ones((3, 2), np.uint8), np.ones((2, 3), np.uint16), np.ones((2, 3, 3), np.uint8)])
def test_no_resizing_broadcasting_or_bit_depth_conversion(dark):
    processor = PreviewProcessor()
    processor.load_dark(dark)
    processor.enable(True)
    result = processor.process(np.ones((2, 3), np.uint8), CTX)
    assert not result.corrected and "mismatch" in result.dark_status


def test_imported_image_is_unverified_and_bound_once_clear_and_cancel():
    processor = PreviewProcessor()
    processor.load_dark(np.ones((2, 3), np.uint8))
    processor.enable(True)
    assert "unverified" in processor.process(np.ones((2, 3), np.uint8), CTX).dark_status
    assert not processor.process(np.ones((2, 3), np.uint8), replace(CTX, gain=2)).corrected
    processor.clear_dark()
    processor.capture_dark()
    processor.cancel_capture()
    processor.process(np.ones((2, 3), np.uint8), CTX)
    with pytest.raises(ValueError, match="No dark"):
        processor.dark_snapshot()


@pytest.mark.parametrize("array", [np.array([]), np.zeros((2, 2), np.float32), np.zeros((2, 2, 2), np.uint8),
                                   np.zeros((1, 2, 3, 4), np.uint8)])
def test_unsupported_raw_rejected(array):
    with pytest.raises(ValueError):
        raw_frame(array)


def test_bgr_channels_preserved_and_latest_only_mailbox():
    processor, mailbox = PreviewProcessor(), LatestPreview()
    frame = np.array([[[1, 2, 3]]], dtype=np.uint8)
    for _ in range(100):
        mailbox.put(processor.process(frame, CTX))
    result = mailbox.take()
    assert result.sequence == 100 and mailbox.replaced == 99
    assert result.pixels.tolist() == [[[1, 2, 3]]]
    assert mailbox.take() is None


@pytest.mark.parametrize("dtype", [np.uint8, np.uint16])
def test_npz_archive_roundtrip_and_npy_raw_bgr(tmp_path, dtype):
    frame = np.arange(36, dtype=dtype).reshape(3, 4, 3)
    path = tmp_path / "dark.npz"
    save_dark_archive(path, frame, CTX)
    loaded, context = load_numeric_dark(path)
    assert np.array_equal(frame, loaded) and context == CTX
    np.save(tmp_path / "dark.npy", frame)
    loaded, context = load_numeric_dark(tmp_path / "dark.npy")
    assert np.array_equal(frame, loaded) and context is None


def test_tiff_rgb_to_bgr_and_monochrome_depth(tmp_path):
    tifffile = pytest.importorskip("tifffile")
    rgb = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    path = tmp_path / "rgb.tif"
    tifffile.imwrite(path, rgb, photometric="rgb")
    assert np.array_equal(load_numeric_dark(path)[0], rgb[..., ::-1])
    mono = np.arange(6, dtype=np.uint16).reshape(2, 3)
    tifffile.imwrite(path, mono, photometric="minisblack")
    assert np.array_equal(load_numeric_dark(path)[0], mono)


def test_pickle_stack_and_invalid_archive_rejected(tmp_path):
    np.save(tmp_path / "object.npy", np.array([object()], dtype=object))
    with pytest.raises(ValueError):
        load_numeric_dark(tmp_path / "object.npy")
    np.savez(tmp_path / "bad.npz", frame=np.zeros((2, 2), np.uint8), metadata=json.dumps({"schema_version": True}))
    with pytest.raises(ValueError):
        load_numeric_dark(tmp_path / "bad.npz")
    tifffile = pytest.importorskip("tifffile")
    tifffile.imwrite(tmp_path / "stack.tif", np.zeros((2, 3, 4), np.uint8), photometric="minisblack")
    with pytest.raises(ValueError, match="single-frame"):
        load_numeric_dark(tmp_path / "stack.tif")


@pytest.mark.parametrize("failure", [False, True])
def test_pump_one_thread_handle_cleanup_bounded_mailbox_and_no_artificial_delay(failure):
    caller = get_ident()
    stop, targets, processor, mailbox = Event(), CameraTargets(), PreviewProcessor(), LatestPreview()
    calls, threads = [], []

    class Camera:
        def __init__(self, **kwargs):
            self.count = 0
            self.exposure = kwargs["exposure_s"]
            self.gain = 1
            threads.append(get_ident())

        def __enter__(self):
            calls.append("enter")
            return self

        def __exit__(self, *args):
            calls.append("close")
            threads.append(get_ident())

        def get_max_gains(self):
            return (4,)

        def set_master_gain(self, gain):
            self.gain = gain
            return gain

        def get_exposure(self):
            return self.exposure

        def get_device_info(self):
            return "test-only camera"

        def start_live(self, *, buffer_frames):
            assert buffer_frames == 3
            calls.append("start")

        def read_latest(self, **kwargs):
            threads.append(get_ident())
            self.count += 1
            if failure:
                raise RuntimeError("test read failure")
            if self.count == 6:
                stop.set()
            return np.full((3, 4), self.count, np.uint8)

    def run():
        pump_camera(targets=targets, processor=processor, mailbox=mailbox, stop=stop,
                    connected=lambda info: calls.append(info), factory=Camera)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run)
        if failure:
            with pytest.raises(RuntimeError, match="test read failure"):
                future.result()
        else:
            future.result()
    assert calls[-1] == "close" and len(set(threads)) == 1 and threads[0] != caller
    if not failure:
        assert mailbox.take().sequence == 5 and mailbox.replaced == 4


def test_cancel_before_worker_start_never_constructs_camera():
    stop = Event()
    stop.set()

    def forbidden(**kwargs):
        pytest.fail("Cancelled preview constructed a camera")

    pump_camera(targets=CameraTargets(), processor=PreviewProcessor(), mailbox=LatestPreview(), stop=stop,
                connected=lambda info: None, factory=forbidden)
