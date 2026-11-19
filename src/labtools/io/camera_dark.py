"""Raw camera dark archives/images. No pickle, resizing, broadcasting or bit-depth guessing."""

import json
import math
from pathlib import Path

import numpy as np

from labtools.processing.camera_preview import CameraContext, raw_frame

MAX_BYTES = 256 * 1024 * 1024


def load_numeric_dark(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Dark file exceeds 256 MiB")
    suffix = path.suffix.lower()
    context = None
    if suffix == ".npz":
        import zipfile

        with zipfile.ZipFile(path) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
                raise ValueError("Expanded dark archive exceeds 256 MiB")
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {"frame", "metadata"}:
                raise ValueError("Expected a Labtools camera dark archive")
            metadata = json.loads(str(archive["metadata"].item()))
            if (not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int
                    or metadata["schema_version"] != 1 or metadata.get("colour_order") != "BGR"):
                raise ValueError("Unsupported dark archive metadata")
            frame = archive["frame"].copy()
            if metadata.get("context") is not None:
                context = CameraContext(**metadata["context"])
    elif suffix == ".npy":
        frame = np.load(path, allow_pickle=False, mmap_mode="r")
        if frame.nbytes > MAX_BYTES:
            raise ValueError("Expanded dark image exceeds 256 MiB")
    elif suffix in {".tif", ".tiff"}:
        import tifffile

        with tifffile.TiffFile(path) as image:
            if len(image.pages) != 1:
                raise ValueError("Load a single-frame TIFF, not a stack")
            page = image.pages[0]
            if math.prod(page.shape) * page.dtype.itemsize > MAX_BYTES:
                raise ValueError("Expanded TIFF exceeds 256 MiB")
            if int(page.photometric) not in (1, 2):
                raise ValueError("TIFF must be black-is-zero monochrome or RGB")
            frame = page.asarray()
            if int(page.photometric) == 2:
                if frame.ndim != 3 or frame.shape[-1] not in (3, 4):
                    raise ValueError("Expected interleaved RGB TIFF")
                frame = frame[..., :3][..., ::-1]  # TIFF RGB -> camera BGR.
    else:
        raise ValueError("Numeric dark formats: .npz, .npy, .tif, .tiff")
    return np.array(raw_frame(frame), copy=True, order="C"), context


def save_dark_archive(path, frame, context):
    from dataclasses import asdict

    metadata = {"schema_version": 1, "colour_order": "BGR",
                "context": None if context is None else asdict(context)}
    with Path(path).open("wb") as handle:
        np.savez_compressed(handle, frame=raw_frame(frame), metadata=json.dumps(metadata))
