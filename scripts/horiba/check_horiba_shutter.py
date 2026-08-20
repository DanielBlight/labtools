"""Acquire and plot three open- and three closed-shutter HORIBA frames.

The frames are acquired in alternating order to reduce the influence of slow
source or detector drift:

    closed 1, open 1, closed 2, open 2, closed 3, open 3

The script does not save data. It displays:

1. All six raw spectra.
2. The mean open and mean closed spectra.
3. The mean open-minus-closed spectrum.

Run this script from the labtools project root so the labtools package is
available in the active uv environment.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray

from labtools.devices.horiba_spectrometer import HoribaSpectrometer

# -----------------------------------------------------------------------------
# Test settings
# -----------------------------------------------------------------------------
PRESET = "syncerity"
TEST_WAVELENGTH_NM = 690.0
EXPOSURE_TIME_S = 0.05
GAIN = 2
SPEED = 0
NUMBER_OF_PAIRS = 3


@dataclass(frozen=True)
class ShutterTestResult:
    """Acquired wavelength axis and shutter-test frame stacks."""

    wavelength_nm: NDArray[np.float64]
    open_frames: NDArray[np.float64]
    closed_frames: NDArray[np.float64]


def describe_frame(label: str, intensity: NDArray[np.float64]) -> None:
    """Print descriptive statistics for one detector frame."""
    print(
        f"{label:10s}  "
        f"mean={np.mean(intensity):12.3f}  "
        f"median={np.median(intensity):12.3f}  "
        f"min={np.min(intensity):12.3f}  "
        f"max={np.max(intensity):12.3f}  "
        f"std={np.std(intensity):12.3f}"
    )


def validate_axis(
    reference: NDArray[np.float64],
    candidate: NDArray[np.float64],
    label: str,
) -> None:
    """Confirm that all frames use the same wavelength axis."""
    if reference.shape != candidate.shape:
        raise RuntimeError(
            f"{label} wavelength-axis shape differs from the first frame: "
            f"{candidate.shape} versus {reference.shape}."
        )

    if not np.allclose(reference, candidate, rtol=0.0, atol=1e-8):
        maximum_difference = float(np.max(np.abs(reference - candidate)))
        raise RuntimeError(
            f"{label} wavelength values differ from the first frame. "
            f"Maximum difference: {maximum_difference:.6g} nm."
        )


async def acquire_shutter_test() -> ShutterTestResult:
    """Acquire three alternating closed/open frame pairs."""
    spec = HoribaSpectrometer(preset=PRESET)

    reference_x: NDArray[np.float64] | None = None
    open_frames: list[NDArray[np.float64]] = []
    closed_frames: list[NDArray[np.float64]] = []

    try:
        print("Connecting to HORIBA devices...")
        await spec.connect()

        await spec.configure(
            gain=GAIN,
            speed=SPEED,
            exposure_time=EXPOSURE_TIME_S,
            roi={},
        )

        actual_wavelength_nm = await spec.set_wavelength(TEST_WAVELENGTH_NM)

        print(f"Requested centre wavelength: {TEST_WAVELENGTH_NM:.3f} nm")
        print(f"Reported centre wavelength:  {actual_wavelength_nm:.3f} nm")
        print(f"Exposure time:               {EXPOSURE_TIME_S:.3f} s")
        print(f"Gain index:                  {GAIN}")
        print(f"Speed index:                 {SPEED}")
        print()

        for pair_index in range(1, NUMBER_OF_PAIRS + 1):
            print(
                f"Acquiring pair {pair_index}/{NUMBER_OF_PAIRS}: "
                "closed then open"
            )

            closed_x, closed_y = await spec.acquire_frame(open_shutter=False)
            open_x, open_y = await spec.acquire_frame(open_shutter=True)

            closed_x = np.asarray(closed_x, dtype=float)
            closed_y = np.asarray(closed_y, dtype=float)
            open_x = np.asarray(open_x, dtype=float)
            open_y = np.asarray(open_y, dtype=float)

            if reference_x is None:
                reference_x = closed_x
            else:
                validate_axis(reference_x, closed_x, f"Closed {pair_index}")

            validate_axis(reference_x, open_x, f"Open {pair_index}")

            closed_frames.append(closed_y)
            open_frames.append(open_y)

        if reference_x is None:
            raise RuntimeError("No shutter-test frames were acquired.")

        return ShutterTestResult(
            wavelength_nm=reference_x,
            open_frames=np.stack(open_frames),
            closed_frames=np.stack(closed_frames),
        )

    finally:
        try:
            await spec.disconnect()
        except Exception as exc:  # noqa: BLE001
            print(f"Disconnect warning: {exc}")


def print_diagnostics(result: ShutterTestResult) -> None:
    """Print frame statistics and comparisons."""
    print()
    print("Individual frame statistics")
    print("---------------------------")

    for index, frame in enumerate(result.closed_frames, start=1):
        describe_frame(f"Closed {index}", frame)

    for index, frame in enumerate(result.open_frames, start=1):
        describe_frame(f"Open {index}", frame)

    mean_closed = np.mean(result.closed_frames, axis=0)
    mean_open = np.mean(result.open_frames, axis=0)
    corrected = mean_open - mean_closed

    print()
    print("Mean spectra")
    print("------------")
    describe_frame("Closed avg", mean_closed)
    describe_frame("Open avg", mean_open)
    describe_frame("Difference", corrected)

    print()
    print("Exact-equality checks")
    print("---------------------")

    for pair_index in range(NUMBER_OF_PAIRS):
        identical = np.array_equal(
            result.closed_frames[pair_index],
            result.open_frames[pair_index],
        )
        print(
            f"Closed {pair_index + 1} exactly equals "
            f"Open {pair_index + 1}: {identical}"
        )

    print(
        "All three closed frames exactly equal: "
        f"{np.array_equal(result.closed_frames[0], result.closed_frames[1]) and np.array_equal(result.closed_frames[1], result.closed_frames[2])}"
    )
    print(
        "All three open frames exactly equal:   "
        f"{np.array_equal(result.open_frames[0], result.open_frames[1]) and np.array_equal(result.open_frames[1], result.open_frames[2])}"
    )


def plot_results(result: ShutterTestResult) -> None:
    """Plot all six frames, their averages, and the mean difference."""
    order = np.argsort(result.wavelength_nm)
    wavelength_nm = result.wavelength_nm[order]

    open_frames = result.open_frames[:, order]
    closed_frames = result.closed_frames[:, order]

    mean_open = np.mean(open_frames, axis=0)
    mean_closed = np.mean(closed_frames, axis=0)
    corrected = mean_open - mean_closed

    figure, axes = plt.subplots(
        3,
        1,
        figsize=(12, 10),
        sharex=True,
    )

    for index, frame in enumerate(closed_frames, start=1):
        axes[0].plot(
            wavelength_nm,
            frame,
            linewidth=1.0,
            label=f"Closed {index}",
        )

    for index, frame in enumerate(open_frames, start=1):
        axes[0].plot(
            wavelength_nm,
            frame,
            linewidth=1.0,
            label=f"Open {index}",
        )

    axes[0].set_title(
        "HORIBA shutter test: three closed and three open acquisitions"
    )
    axes[0].set_ylabel("Intensity (counts)")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(ncols=3)

    axes[1].plot(
        wavelength_nm,
        mean_closed,
        linewidth=1.4,
        label="Mean closed",
    )
    axes[1].plot(
        wavelength_nm,
        mean_open,
        linewidth=1.4,
        label="Mean open",
    )
    axes[1].set_ylabel("Mean intensity")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    axes[2].plot(
        wavelength_nm,
        corrected,
        color="black",
        linewidth=1.2,
        label="Mean open - mean closed",
    )
    axes[2].axhline(0.0, color="grey", linewidth=0.8)
    axes[2].set_xlabel("Wavelength (nm)")
    axes[2].set_ylabel("Difference (counts)")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()

    figure.suptitle(
        f"Centre {TEST_WAVELENGTH_NM:.1f} nm, "
        f"exposure {EXPOSURE_TIME_S:.3f} s",
        y=0.995,
    )
    figure.tight_layout()
    plt.show()


def main() -> None:
    """Acquire, report, and plot the shutter-test frames."""
    result = asyncio.run(acquire_shutter_test())
    print_diagnostics(result)
    plot_results(result)


if __name__ == "__main__":
    main()
