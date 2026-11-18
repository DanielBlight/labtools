"""Deterministic toy range spectra, NOT a HORIBA SDK or physical shutter model."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import numpy as np

from labtools.acquisition.spectrum_service import RangeBackend
from labtools.config.spectrum import SpectrumSettings


@asynccontextmanager
async def open_simulated_range(
    settings: SpectrumSettings,
) -> AsyncIterator[RangeBackend]:
    settings.validate()
    if settings.backend != "simulation":
        raise ValueError("Synthetic adapter refuses real settings")
    x = np.linspace(settings.start_nm, settings.end_nm, 64)
    dark = np.full(x.shape, 10.0 + settings.exposure_s * 2.0)
    center = (settings.start_nm + settings.end_nm) / 2
    width = (settings.end_nm - settings.start_nm) / 10
    signal = settings.exposure_s * (
        100 + 1000 * np.exp(-0.5 * ((x - center) / width) ** 2)
    )
    closed = False

    class Backend:
        async def capture_dark(self) -> tuple[np.ndarray, np.ndarray]:
            if closed:
                raise RuntimeError("Synthetic spectrum backend is closed")
            return x.copy(), dark.copy()

        async def acquire(self, dark_mode: str) -> tuple[np.ndarray, np.ndarray]:
            if closed:
                raise RuntimeError("Synthetic spectrum backend is closed")
            if dark_mode not in {"none", "per_center", "per_frame"}:
                raise ValueError("Unsupported synthetic dark mode")
            # Identical deterministic frames have identical reductions in every
            # supported mode. No noise, timing, stitching or electronics model.
            return x.copy(), (signal + dark if dark_mode == "none" else signal).copy()

    try:
        yield Backend()
    finally:
        closed = True


@asynccontextmanager
async def open_simulated_alignment(settings):
    settings.validate()
    if settings.backend != "simulation":
        raise ValueError("Synthetic alignment adapter refuses real settings")

    class Backend:
        actual_centre_nm = float(settings.centre_nm)

        async def capture(self, subtract_dark):
            x = np.linspace(settings.centre_nm - 5.0, settings.centre_nm + 5.0, 64)
            raw = 100.0 + 900.0 * np.exp(-0.5 * ((x - settings.centre_nm) / 0.8) ** 2)
            dark = np.full_like(raw, 10.0)
            return x, raw - dark if subtract_dark else raw.copy(), raw

    yield Backend()


# These options describe the existing toy backend, not a physical detector preset.
TOY_PRESET_OPTIONS = {
    "syncerity": {
        "gains": (("Toy gain (no detector)", 0),),
        "speeds": (("Toy speed (no detector)", 0),),
        "default_gain": 0,
        "default_speed": 0,
        "minimum_exposure_s": 0.065,
    },
}


def main(argv=None):
    """Launch the existing spectrum GUI with an explicit synthetic backend."""
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Synthetic spectrum GUI; no hardware")
    parser.add_argument("--gui", action="store_true", help="Open the synthetic operator window")
    parser.add_argument("--output", type=Path, default=Path.home() / "Labtools Simulation" / "Spectra")
    args = parser.parse_args(argv)
    if not args.gui:
        parser.error("Use --gui; for the saved end-to-end rehearsal use examples/measurements/rehearse_spectrum.py")
    from PyQt6.QtWidgets import QApplication

    from labtools.gui.spectrum_gui_horiba import HoribaRangeWindow

    app = QApplication([sys.argv[0]])
    window = HoribaRangeWindow(
        backend="simulation", configuration_id="toy-scene-v1",
        preset_options=TOY_PRESET_OPTIONS,
    )
    window.start_wl.setValue(500.0)
    window.end_wl.setValue(600.0)
    window.exposure_box.setValue(0.065)
    window.output_directory.setText(str(args.output.expanduser()))
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
