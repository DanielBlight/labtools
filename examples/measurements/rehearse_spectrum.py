"""One synthetic spectroscopy workflow using existing measurement/archive APIs.

No Qt window, hardware backend, new simulator or approval of instrument settings.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from labtools.io.spectrum_records import save_spectrum_result
from labtools.measurements.recipes import load_recipe
from labtools.measurements.spectrum import (
    SpectrumRuntime,
    acquire_spectrum,
    acquire_spectrum_async,
    capture_dark,
    load_dark,
    save_dark,
)


def _allocate(root: Path) -> Path:
    parent = root.expanduser().resolve() / "SIMULATION"
    parent.mkdir(parents=True, exist_ok=True)
    stem = datetime.now(UTC).strftime("spectrum_%Y%m%d-%H%M%S-%f")
    for index in range(1000):
        path = parent / (stem if index == 0 else f"{stem}-{index:03d}")
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path
    raise FileExistsError("Could not allocate a distinct synthetic output directory")


def rehearse(recipe_path: Path, output_root: Path) -> dict:
    """Complete, export and reopen a synthetic spectrum/dark/repeat sequence."""
    recipe_path = Path(recipe_path)
    recipe = load_recipe(recipe_path)
    if recipe.kind != "spectrum" or recipe.backend != "simulation":
        raise ValueError("Use a spectrum recipe with backend='simulation'; real execution is refused")
    request = recipe.request
    if request.dark_mode != "none" or request.dark is not None:
        raise ValueError("Start with dark_mode='none' and no dark record; this rehearsal captures its own")
    # Reject before creating a runtime or output if the recipe is unsuitable.
    output = _allocate(Path(output_root))
    (output / "SYNTHETIC_DATA.txt").write_text(
        "Synthetic spectroscopy rehearsal only; not experimental or calibration data.\n",
        encoding="utf-8",
    )
    report = {
        "status": "running", "synthetic_data": True,
        "configuration_id": request.settings.configuration_id,
        "settings": asdict(request.settings),
        "recipe_sha256": hashlib.sha256(recipe_path.read_bytes()).hexdigest(),
        "output_directory": str(output), "checks": {},
        "limitations": "Toy spectrum only: no Qt, timing, detector, optics or physical shutter validation",
    }
    report_path = output / "rehearsal.json"
    try:
        with SpectrumRuntime(backend="simulation") as runtime:
            raw = acquire_spectrum(request, runtime=runtime).result
            dark = capture_dark(request, runtime=runtime)
            save_dark(output / "dark.npz", dark)
            restored_dark = load_dark(output / "dark.npz")
            assert restored_dark.record_id == dark.record_id
            np.testing.assert_array_equal(restored_dark.intensity, dark.intensity)
            corrected_request = replace(request, dark_mode="pre_taken", dark=restored_dark)
            corrected = acquire_spectrum(corrected_request, runtime=runtime).result
            repeated = acquire_spectrum(corrected_request, runtime=runtime).result
            np.testing.assert_allclose(corrected.intensity, raw.intensity - restored_dark.intensity)
            np.testing.assert_array_equal(repeated.intensity, corrected.intensity)
            report["checks"].update(dark_roundtrip=True, subtraction=True, repeat=True)

            # Cooperative cancellation before opening the existing backend, not a timing test.
            try:
                asyncio.run(acquire_spectrum_async(request, runtime=runtime, cancel_requested=lambda: True))
            except asyncio.CancelledError:
                report["checks"]["cancel_before_acquisition"] = True
            else:
                raise AssertionError("Cancellation did not propagate")
            after_cancel = acquire_spectrum(corrected_request, runtime=runtime).result
            np.testing.assert_array_equal(after_cancel.intensity, corrected.intensity)
            report["checks"]["reuse_after_cancellation"] = True

            mismatched = replace(request.settings, exposure_s=request.settings.exposure_s * 2)
            try:
                restored_dark.validate_for(mismatched)
            except ValueError:
                report["checks"]["mismatched_dark_rejected"] = True
            else:
                raise AssertionError("Mismatched dark was accepted")

        save_spectrum_result(output / "raw_spectrum.npz", raw)
        save_spectrum_result(output / "corrected_spectrum.npz", corrected)
        with np.load(output / "corrected_spectrum.npz", allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"].item()))
            assert metadata["synthetic_data"] and metadata["settings"]["backend"] == "simulation"
            assert metadata["dark_record_id"] == restored_dark.record_id
            np.testing.assert_array_equal(archive["intensity"], corrected.intensity)
            report["checks"]["spectrum_archive_reopened"] = True
        with (output / "spectrum.csv").open("x", newline="", encoding="utf-8") as handle:
            handle.write("# SYNTHETIC DATA ONLY; authoritative settings are in rehearsal.json and NPZ metadata\n")
            writer = csv.writer(handle)
            writer.writerow(["wavelength_nm", "raw_intensity", "dark_intensity", "corrected_intensity"])
            writer.writerows(zip(raw.wavelength_nm, raw.intensity, dark.intensity, corrected.intensity, strict=True))

        # Render data with Agg, never import pyplot or a Qt backend.
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=(8, 5))
        FigureCanvasAgg(figure)
        axes = figure.subplots()
        axes.plot(raw.wavelength_nm, raw.intensity, label="Raw synthetic")
        axes.plot(dark.wavelength_nm, dark.intensity, label="Stored synthetic dark")
        axes.plot(corrected.wavelength_nm, corrected.intensity, label="Dark-subtracted synthetic")
        axes.set(title="SYNTHETIC spectrum rehearsal", xlabel="Wavelength (nm)", ylabel="Toy intensity (arbitrary units)")
        axes.legend()
        figure.tight_layout()
        figure.savefig(output / "spectrum.png")
        report["points"] = int(raw.wavelength_nm.size)
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path.home() / "Labtools Simulation" / "Spectra")
    args = parser.parse_args(argv)
    try:
        report = rehearse(args.recipe, args.output)
    except (OSError, ValueError, AssertionError) as error:
        parser.exit(1, f"Rehearsal failed: {error}\n")
    print("SYNTHETIC SPECTROSCOPY REHEARSAL PASSED")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
