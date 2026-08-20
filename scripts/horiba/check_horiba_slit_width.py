"""Compare open-shutter HORIBA spectra at several slit widths.

The test holds detector configuration, wavelength, exposure, gain, speed, and
shutter state constant while varying one monochromator slit. No data are saved.

The original slit position is restored before disconnecting.
"""

from __future__ import annotations

import asyncio

import matplotlib.pyplot as plt
import numpy as np
from horiba_sdk.devices.single_devices.monochromator import (
    Monochromator,
)

from labtools.devices.horiba_spectrometer import (
    HoribaSpectrometer,
)


# ----------------------------------------------------------------------
# Test settings
# ----------------------------------------------------------------------
PRESET = "syncerity"

# Choose a centre wavelength where a measurable optical signal is expected.
TEST_WAVELENGTH_NM = 690

# Start conservatively to avoid saturation at wider slit positions.
EXPOSURE_TIME_S = 0.05

GAIN = 2
SPEED = 0

# Change this to B, C, or D if slit A is not in the active optical path.
SLIT_TO_TEST = Monochromator.Slit.A

# Slit widths to compare, in millimetres.
SLIT_WIDTHS_MM = [
    0.05,
    0.10,
    0.25,
    0.50,
    1.00,
    2.00
]


async def wait_for_monochromator(
    monochromator: Monochromator,
    timeout_s: float = 60.0,
    poll_interval_s: float = 0.1,
) -> None:
    """Wait until the monochromator reports that it is idle."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s

    while await monochromator.is_busy():
        if loop.time() >= deadline:
            raise TimeoutError(
                "The monochromator remained busy for more than "
                f"{timeout_s:.1f} seconds."
            )

        await asyncio.sleep(poll_interval_s)


async def report_available_slits(
    monochromator: Monochromator,
) -> None:
    """Print the reported position of every configured slit."""
    print()
    print("Current slit positions")

    for slit in Monochromator.Slit:
        try:
            position_mm = (
                await monochromator.get_slit_position_in_mm(
                    slit
                )
            )

            print(
                f"  Slit {slit.name}: "
                f"{position_mm:.6f} mm"
            )

        except Exception as exc:
            print(
                f"  Slit {slit.name}: "
                f"readback failed: {exc}"
            )


def print_spectrum_statistics(
    slit_width_mm: float,
    intensity: np.ndarray,
) -> None:
    """Print summary statistics for one acquired spectrum."""
    print(
        f"  Slit readback:      "
        f"{slit_width_mm:.6f} mm"
    )

    print(
        f"  Mean counts:        "
        f"{np.mean(intensity):.3f}"
    )

    print(
        f"  Median counts:      "
        f"{np.median(intensity):.3f}"
    )

    print(
        f"  Maximum counts:     "
        f"{np.max(intensity):.3f}"
    )

    print(
        f"  Integrated counts:  "
        f"{np.sum(intensity):.3f}"
    )

    print(
        f"  Standard deviation: "
        f"{np.std(intensity):.3f}"
    )


async def acquire_slit_sweep() -> list[
    tuple[
        float,
        np.ndarray,
        np.ndarray,
    ]
]:
    """Acquire one open-shutter spectrum at each requested slit width."""
    spec = HoribaSpectrometer(
        preset=PRESET
    )

    original_slit_width_mm: float | None = None

    spectra: list[
        tuple[
            float,
            np.ndarray,
            np.ndarray,
        ]
    ] = []

    try:
        print(
            "Connecting to the HORIBA spectrometer..."
        )

        await spec.connect()

        await spec.configure(
            gain=GAIN,
            speed=SPEED,
            exposure_time=EXPOSURE_TIME_S,
            roi={},
        )

        await report_available_slits(
            spec.mono
        )

        original_slit_width_mm = (
            await spec.mono.get_slit_position_in_mm(
                SLIT_TO_TEST
            )
        )

        print()
        print(
            f"Original slit {SLIT_TO_TEST.name} "
            f"position: "
            f"{original_slit_width_mm:.6f} mm"
        )

        actual_wavelength_nm = (
            await spec.set_wavelength(
                TEST_WAVELENGTH_NM
            )
        )

        print(
            f"Requested centre wavelength: "
            f"{TEST_WAVELENGTH_NM:.3f} nm"
        )

        print(
            f"Reported centre wavelength:  "
            f"{actual_wavelength_nm:.3f} nm"
        )

        # Do not call mono.open_shutter() here. The connected ICL
        # configuration rejects the explicit monochromator shutter command.
        #
        # Each acquisition below requests an open-shutter exposure through:
        #
        #     spec.acquire_frame(open_shutter=True)
        #
        # which calls the CCD acquisition API.

        print(
            "The slit sweep will request an open shutter "
            "through each CCD acquisition."
        )

        for requested_width_mm in SLIT_WIDTHS_MM:
            print()
            print(
                f"Setting slit {SLIT_TO_TEST.name} to "
                f"{requested_width_mm:.3f} mm..."
            )

            await spec.mono.set_slit_position(
                SLIT_TO_TEST,
                requested_width_mm,
            )

            await wait_for_monochromator(
                spec.mono
            )

            reported_width_mm = (
                await spec.mono.get_slit_position_in_mm(
                    SLIT_TO_TEST
                )
            )

            wavelength_nm, intensity = (
                await spec.acquire_frame(
                    open_shutter=True
                )
            )

            wavelength_nm = np.asarray(
                wavelength_nm,
                dtype=float,
            )

            intensity = np.asarray(
                intensity,
                dtype=float,
            )

            print_spectrum_statistics(
                reported_width_mm,
                intensity,
            )

            spectra.append(
                (
                    reported_width_mm,
                    wavelength_nm,
                    intensity,
                )
            )

    finally:
        if (
            spec.mono is not None
            and original_slit_width_mm is not None
        ):
            try:
                print()
                print(
                    f"Restoring slit "
                    f"{SLIT_TO_TEST.name} to "
                    f"{original_slit_width_mm:.6f} mm..."
                )

                await spec.mono.set_slit_position(
                    SLIT_TO_TEST,
                    original_slit_width_mm,
                )

                await wait_for_monochromator(
                    spec.mono
                )

                restored_width_mm = (
                    await spec.mono.get_slit_position_in_mm(
                        SLIT_TO_TEST
                    )
                )

                print(
                    f"Restored slit position: "
                    f"{restored_width_mm:.6f} mm"
                )

            except Exception as exc:
                print(
                    "WARNING: Failed to restore the "
                    f"original slit position: {exc}"
                )

        try:
            await spec.disconnect()

        except Exception as exc:
            print(
                f"Disconnect warning: {exc}"
            )

    return spectra


def plot_spectra(
    spectra: list[
        tuple[
            float,
            np.ndarray,
            np.ndarray,
        ]
    ],
) -> None:
    """Plot all slit-width spectra on the same axes."""
    if not spectra:
        raise RuntimeError(
            "No spectra were acquired."
        )

    figure, axes = plt.subplots(
        figsize=(11, 7)
    )

    for (
        slit_width_mm,
        wavelength_nm,
        intensity,
    ) in spectra:
        # Sort by wavelength so each curve is plotted left to right.
        order = np.argsort(
            wavelength_nm
        )

        axes.plot(
            wavelength_nm[order],
            intensity[order],
            linewidth=1.25,
            label=(
                f"Slit {SLIT_TO_TEST.name}: "
                f"{slit_width_mm:.3f} mm"
            ),
        )

    axes.set_title(
        "HORIBA slit-width comparison\n"
        f"Centre wavelength: "
        f"{TEST_WAVELENGTH_NM:.1f} nm, "
        f"exposure: {EXPOSURE_TIME_S:.3f} s"
    )

    axes.set_xlabel(
        "Wavelength (nm)"
    )

    axes.set_ylabel(
        "Intensity (counts)"
    )

    axes.grid(
        True,
        alpha=0.3,
    )

    axes.legend(
        title="Slit setting"
    )

    figure.tight_layout()

    plt.show()


def main() -> None:
    """Acquire the slit sweep, disconnect, and display the plot."""
    spectra = asyncio.run(
        acquire_slit_sweep()
    )

    plot_spectra(
        spectra
    )


if __name__ == "__main__":
    main()

