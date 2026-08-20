"""Asynchronous HORIBA monochromator and CCD wrapper."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import numpy as np
from horiba_sdk.core.acquisition_format import AcquisitionFormat
from horiba_sdk.core.timer_resolution import TimerResolution
from horiba_sdk.core.x_axis_conversion_type import XAxisConversionType
from horiba_sdk.devices.device_manager import DeviceManager
from horiba_sdk.devices.single_devices.monochromator import Monochromator
from loguru import logger

CombineMode = Literal["single", "mean", "median", "sigma_clip"]
DarkFrameMode = Literal["none", "once", "per_frame"]

_PRESET_TO_CCD_INDEX = {
    "symphony": 0,
    "syncerity": 1,
}


class HoribaSpectrometer:
    """Own one HORIBA DeviceManager, monochromator, and CCD connection.

    All methods on one instance must be called from the same asyncio event
    loop. ``exposure_time`` values at the labtools API boundary are seconds.

    Detector presets select a CCD discovery index only. They do not force a
    grating turret position because the mapping of physical gratings to FIRST,
    SECOND, and THIRD is defined by the spectrometer firmware configuration.
    """

    def __init__(
        self,
        preset: str = "syncerity",
        *,
        ccd_index: int | None = None,
        monochromator_index: int = 0,
        start_icl: bool = True,
    ) -> None:
        preset = preset.lower().strip()

        if ccd_index is None:
            try:
                ccd_index = _PRESET_TO_CCD_INDEX[preset]
            except KeyError as exc:
                raise ValueError(
                    f"Unknown preset {preset!r}; pass ccd_index explicitly."
                ) from exc

        if ccd_index < 0 or monochromator_index < 0:
            raise ValueError("Device indices cannot be negative.")

        self.preset = preset
        self.ccd_index = ccd_index
        self.monochromator_index = monochromator_index
        self._start_icl = start_icl

        self.device_manager: DeviceManager | None = None
        self.mono: Any = None
        self.ccd: Any = None
        self._connected = False
        self._configured = False
        self._exposure_time_s = 0.0
        self._wavelength_conversion_enabled = False

    @property
    def exposure_time_s(self) -> float:
        """Return the configured exposure time in seconds."""
        return self._exposure_time_s

    def _ensure_connected(self) -> None:
        if not self._connected or self.mono is None or self.ccd is None:
            raise RuntimeError("The HORIBA spectrometer is not connected.")

    async def connect(self) -> None:
        """Start ICL, discover devices, and open the selected pair.

        The monochromator connection is verified immediately after ``open()``.
        This prevents subsequent busy-state polling against a USB session that
        ICL has not actually opened.
        """
        if self._connected:
            return

        manager = DeviceManager(start_icl=self._start_icl)
        mono: Any = None

        try:
            await manager.start()

            ccds = list(manager.charge_coupled_devices)
            monos = list(manager.monochromators)

            if not ccds:
                raise RuntimeError("No HORIBA CCD devices were discovered.")

            if not monos:
                raise RuntimeError("No HORIBA monochromators were discovered.")

            if self.ccd_index >= len(ccds):
                raise RuntimeError(
                    f"Requested CCD index {self.ccd_index}, but only "
                    f"{len(ccds)} CCD device(s) were discovered."
                )

            if self.monochromator_index >= len(monos):
                raise RuntimeError(
                    f"Requested monochromator index {self.monochromator_index}, "
                    f"but only {len(monos)} were discovered."
                )

            mono = monos[self.monochromator_index]
            ccd = ccds[self.ccd_index]

            logger.info(
                "Opening HORIBA monochromator index {}",
                self.monochromator_index,
            )

            await mono.open()

            mono_is_open = await mono.is_open()

            if not mono_is_open:
                raise RuntimeError(
                    "ICL returned from mono.open(), but the monochromator "
                    "does not report an open USB connection. Check "
                    "monochromator power, USB connection, ICL state, and "
                    "the configured communication parameters."
                )

            logger.info("HORIBA monochromator USB connection verified open")

            await self._wait_for_mono(mono=mono)
            await ccd.open()

            self.device_manager = manager
            self.mono = mono
            self.ccd = ccd
            self._connected = True

            if not await self.mono.is_initialized():
                logger.info("Initialising HORIBA monochromator")
                await self.mono.initialize()
                await self._wait_for_mono()

        except Exception:
            if mono is not None:
                try:
                    if await mono.is_open():
                        await mono.close()
                except Exception as cleanup_error:  # noqa: BLE001
                    logger.warning(
                        "Monochromator cleanup failed after connection error: {}",
                        cleanup_error,
                    )

            try:
                await manager.stop()
            except Exception as cleanup_error:  # noqa: BLE001
                logger.warning(
                    "DeviceManager cleanup failed after connection error: {}",
                    cleanup_error,
                )

            raise

    async def disconnect(self) -> None:
        """Close all resources, attempting every cleanup step."""
        errors: list[tuple[str, Exception]] = []

        for name, resource, method in (
            ("CCD close", self.ccd, "close"),
            ("monochromator close", self.mono, "close"),
            ("DeviceManager stop", self.device_manager, "stop"),
        ):
            if resource is not None:
                try:
                    await getattr(resource, method)()
                except Exception as exc:  # noqa: BLE001
                    errors.append((name, exc))

        self.device_manager = None
        self.mono = None
        self.ccd = None
        self._connected = False
        self._configured = False
        self._wavelength_conversion_enabled = False

        if errors:
            details = "; ".join(f"{name}: {error}" for name, error in errors)
            raise RuntimeError(f"HORIBA cleanup failures: {details}")

    async def _wait_for_mono(
        self,
        *,
        mono: Any | None = None,
        timeout_s: float = 60.0,
        poll_interval_s: float = 0.25,
    ) -> None:
        """Wait until the monochromator is idle.

        The USB connection is checked before every busy-state query. Polling
        stops immediately if the monochromator no longer reports an open
        connection, preventing repeated ``Mono USB not open`` errors.
        """
        target = mono if mono is not None else self.mono

        if target is None:
            raise RuntimeError("No monochromator is available.")

        if timeout_s <= 0:
            raise ValueError("timeout_s must be greater than zero.")

        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be greater than zero.")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s

        while True:
            try:
                mono_is_open = await target.is_open()
            except Exception as exc:
                raise RuntimeError(
                    "Unable to query the monochromator USB connection state. "
                    "Polling has been stopped."
                ) from exc

            if not mono_is_open:
                raise RuntimeError(
                    "The monochromator USB connection is not open. Polling "
                    "has been stopped to prevent repeated 'Mono USB not "
                    "open' errors."
                )

            try:
                busy = await target.is_busy()
            except Exception as exc:
                raise RuntimeError(
                    "The monochromator became unavailable while waiting for "
                    "it to become idle."
                ) from exc

            if not busy:
                return

            if loop.time() >= deadline:
                raise TimeoutError(
                    "The monochromator remained busy for more than "
                    f"{timeout_s:.1f} seconds."
                )

            await asyncio.sleep(poll_interval_s)

    async def report_current_grating(self) -> Monochromator.Grating:
        """Read and report the current grating turret position.

        Detector preset names are not assumed to identify turret slots. The
        physical grating associated with FIRST, SECOND, or THIRD is defined by
        the spectrometer firmware configuration.
        """
        self._ensure_connected()

        reported_grating = await self.mono.get_turret_grating()

        logger.info(
            "Preset {} is using the currently reported grating turret position: {}",
            self.preset,
            reported_grating.name,
        )

        return reported_grating

    async def configure(
        self,
        *,
        gain: int = 0,
        speed: int = 0,
        exposure_time: float = 0.5,
        roi: dict[str, int] | None = None,
    ) -> None:
        """Configure the CCD for a one-dimensional spectral acquisition."""
        self._ensure_connected()

        await self.report_current_grating()

        if exposure_time <= 0:
            raise ValueError("exposure_time must be greater than zero.")

        config = await self.ccd.get_configuration()
        chip_width = int(config["chipWidth"])
        chip_height = int(config["chipHeight"])

        roi = dict(roi or {})
        x_origin = int(roi.get("x_origin", 0))
        y_origin = int(roi.get("y_origin", 0))
        width = int(roi.get("width", chip_width))
        height = int(roi.get("height", chip_height))
        x_bin = int(roi.get("x_bin", 1))
        y_bin = int(roi.get("y_bin", chip_height))

        if min(width, height, x_bin, y_bin) <= 0:
            raise ValueError("ROI dimensions and binning must be positive.")

        if x_origin < 0 or y_origin < 0:
            raise ValueError("ROI origins cannot be negative.")

        if x_origin + width > chip_width or y_origin + height > chip_height:
            raise ValueError("ROI extends beyond the CCD dimensions.")

        await self.ccd.set_acquisition_format(1, AcquisitionFormat.SPECTRA_IMAGE)
        await self.ccd.set_region_of_interest(
            1,
            x_origin,
            y_origin,
            width,
            height,
            x_bin,
            y_bin,
        )
        await self.ccd.set_acquisition_count(1)
        await self.ccd.set_timer_resolution(TimerResolution.MILLISECONDS)
        await self.ccd.set_exposure_time(round(exposure_time * 1000))
        await self.ccd.set_gain(int(gain))
        await self.ccd.set_speed(int(speed))

        self._exposure_time_s = float(exposure_time)
        self._configured = True
        self._wavelength_conversion_enabled = False

    async def prepare_wavelength_axis(self) -> float:
        """Prepare CCD wavelength conversion using the current mono position."""
        self._ensure_connected()

        if not self._configured:
            raise RuntimeError(
                "Configure the CCD before preparing wavelength conversion."
            )

        await self._wait_for_mono()

        current_wavelength = float(await self.mono.get_current_wavelength())

        await self.ccd.set_center_wavelength(
            self.mono.id(),
            current_wavelength,
        )

        if not self._wavelength_conversion_enabled:
            await self.ccd.set_x_axis_conversion_type(
                XAxisConversionType.FROM_ICL_SETTINGS_INI
            )
            self._wavelength_conversion_enabled = True

        logger.debug(
            "Prepared CCD wavelength conversion at {:.3f} nm",
            current_wavelength,
        )

        return current_wavelength

    async def set_slit_width(self, slit_name: str, width_mm: float) -> float:
        """Set and verify one monochromator slit width.

        The current GUI uses this method only for slit A. The generic argument
        remains useful for diagnostics.
        """
        self._ensure_connected()

        slit_name = slit_name.strip().upper()

        try:
            slit = Monochromator.Slit[slit_name]
        except KeyError as exc:
            valid_names = ", ".join(member.name for member in Monochromator.Slit)
            raise ValueError(
                f"Unknown slit {slit_name!r}. Valid slit names are: {valid_names}."
            ) from exc

        width_mm = float(width_mm)

        if width_mm <= 0:
            raise ValueError("Slit width must be greater than zero.")

        await self.mono.set_slit_position(slit, width_mm)

        # Give ICL time to register the movement before checking busy state.
        await asyncio.sleep(0.5)
        await self._wait_for_mono()

        reported_width_mm = float(await self.mono.get_slit_position_in_mm(slit))

        logger.info(
            "Slit {} requested at {:.4f} mm, reported {:.4f} mm",
            slit.name,
            width_mm,
            reported_width_mm,
        )

        return reported_width_mm

    async def set_wavelength(self, wavelength_nm: float) -> float:
        """Move the monochromator and update CCD wavelength calibration."""
        self._ensure_connected()

        if not self._configured:
            raise RuntimeError("Configure the CCD before setting wavelength.")

        wavelength_nm = float(wavelength_nm)

        await self.mono.move_to_target_wavelength(wavelength_nm)
        await self._wait_for_mono()

        actual_wavelength = float(await self.mono.get_current_wavelength())

        await self.ccd.set_center_wavelength(
            self.mono.id(),
            actual_wavelength,
        )

        if not self._wavelength_conversion_enabled:
            await self.ccd.set_x_axis_conversion_type(
                XAxisConversionType.FROM_ICL_SETTINGS_INI
            )
            self._wavelength_conversion_enabled = True

        logger.debug(
            "Monochromator requested at {:.3f} nm, reported {:.3f} nm",
            wavelength_nm,
            actual_wavelength,
        )

        return actual_wavelength

    async def _start_acquisition(self, *, open_shutter: bool) -> None:
        if not self._configured:
            raise RuntimeError("Configure the CCD before acquiring data.")

        if not await self.ccd.get_acquisition_ready():
            raise RuntimeError("The HORIBA CCD is not ready for acquisition.")

        await self.ccd.acquisition_start(open_shutter=open_shutter)

    async def _wait_for_acquisition_data(
        self,
        *,
        timeout_s: float | None = None,
        poll_interval_s: float = 0.05,
    ) -> dict[str, Any]:
        """Poll for CCD data until available or timed out."""
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be greater than zero.")

        if timeout_s is None:
            timeout_s = max(5.0, self._exposure_time_s * 4.0 + 2.0)

        if timeout_s <= 0:
            raise ValueError("timeout_s must be greater than zero.")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        last_error: Exception | None = None

        await asyncio.sleep(min(max(self._exposure_time_s, 0.01), timeout_s))

        while loop.time() < deadline:
            try:
                if (
                    hasattr(self.ccd, "get_acquisition_busy")
                    and await self.ccd.get_acquisition_busy()
                ):
                    await asyncio.sleep(poll_interval_s)
                    continue

                return await self.ccd.get_acquisition_data()

            except Exception as exc:  # noqa: BLE001
                # The vendor SDK may raise while data is not yet available.
                last_error = exc
                await asyncio.sleep(poll_interval_s)

        raise TimeoutError(
            f"CCD data was not available within {timeout_s:.2f} seconds."
        ) from last_error

    @staticmethod
    def _parse_spectrum(raw_data: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
        """Extract one validated one-dimensional spectrum."""
        try:
            roi = raw_data["acquisition"][0]["roi"][0]
            x_data = np.asarray(roi["xData"], dtype=float)
            y_data = np.asarray(roi["yData"][0], dtype=float)
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected HORIBA acquisition-data structure.") from exc

        if x_data.ndim != 1 or y_data.ndim != 1:
            raise RuntimeError(
                f"Expected 1D spectral data; got {x_data.shape=} and {y_data.shape=}."
            )

        if x_data.shape != y_data.shape:
            raise RuntimeError(
                f"Wavelength and intensity lengths differ: {x_data.size} and "
                f"{y_data.size}."
            )

        if not np.all(np.isfinite(x_data)) or not np.all(np.isfinite(y_data)):
            raise RuntimeError("HORIBA acquisition contains non-finite values.")

        return x_data, y_data

    async def acquire_frame(
        self,
        *,
        open_shutter: bool,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire one open- or closed-shutter CCD frame."""
        self._ensure_connected()
        await self._start_acquisition(open_shutter=open_shutter)
        raw_data = await self._wait_for_acquisition_data()
        return self._parse_spectrum(raw_data)

    @staticmethod
    def _combine_frames(frames: np.ndarray, mode: CombineMode) -> np.ndarray:
        """Combine a stack with shape ``(frames, pixels)``."""
        if frames.ndim != 2 or frames.shape[0] == 0:
            raise ValueError("frames must have shape (n_frames, n_pixels).")

        if mode == "single":
            return frames[0]

        if mode == "mean":
            return np.mean(frames, axis=0)

        if mode == "median":
            return np.median(frames, axis=0)

        if mode == "sigma_clip":
            if frames.shape[0] < 3:
                raise ValueError("sigma_clip requires at least three frames.")

            median = np.median(frames, axis=0)
            mad = np.median(np.abs(frames - median), axis=0)
            robust_sigma = 1.4826 * mad
            keep = np.abs(frames - median) <= 3.0 * robust_sigma
            keep[:, robust_sigma == 0] = True
            result = np.nanmean(np.where(keep, frames, np.nan), axis=0)
            return np.where(np.isnan(result), median, result)

        raise ValueError("mode must be 'single', 'mean', 'median', or 'sigma_clip'.")

    async def get_spectrum(
        self,
        *,
        n_frames: int = 1,
        mode: CombineMode = "single",
        dark_frame_mode: DarkFrameMode = "none",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire and combine spectra at the current centre wavelength.

        ``once`` takes one dark at the centre and subtracts it from every
        repeated signal. ``per_frame`` pairs every signal with a new dark.
        """
        if n_frames < 1:
            raise ValueError("n_frames must be at least one.")

        if mode == "single" and n_frames != 1:
            raise ValueError("single mode requires n_frames=1.")

        if dark_frame_mode not in {"none", "once", "per_frame"}:
            raise ValueError("Invalid dark_frame_mode.")

        reference_x: np.ndarray | None = None
        one_dark: np.ndarray | None = None

        if dark_frame_mode == "once":
            reference_x, one_dark = await self.acquire_frame(open_shutter=False)

        corrected: list[np.ndarray] = []

        for _ in range(n_frames):
            x_data, signal = await self.acquire_frame(open_shutter=True)

            if reference_x is None:
                reference_x = x_data
            elif reference_x.shape != x_data.shape or not np.allclose(
                reference_x,
                x_data,
                rtol=0.0,
                atol=1e-8,
            ):
                raise RuntimeError("Wavelength axes changed between frames.")

            if dark_frame_mode == "per_frame":
                dark_x, dark = await self.acquire_frame(open_shutter=False)

                if dark_x.shape != x_data.shape or not np.allclose(
                    dark_x,
                    x_data,
                    rtol=0.0,
                    atol=1e-8,
                ):
                    raise RuntimeError("Dark and signal wavelength axes differ.")

                signal = signal - dark

            elif one_dark is not None:
                if one_dark.shape != signal.shape:
                    raise RuntimeError("Dark and signal frame shapes differ.")

                signal = signal - one_dark

            corrected.append(signal)

        if reference_x is None:
            raise RuntimeError("No signal frames were acquired.")

        return reference_x, self._combine_frames(np.stack(corrected), mode)

    async def get_dark_spectrum(
        self,
        *,
        n_frames: int = 1,
        mode: CombineMode = "single",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire and combine closed-shutter frames at the current centre."""
        if n_frames < 1:
            raise ValueError("n_frames must be at least one.")

        if mode == "single" and n_frames != 1:
            raise ValueError("single mode requires n_frames=1.")

        reference_x: np.ndarray | None = None
        frames: list[np.ndarray] = []

        for _ in range(n_frames):
            x_data, dark = await self.acquire_frame(open_shutter=False)

            if reference_x is None:
                reference_x = x_data
            elif reference_x.shape != x_data.shape or not np.allclose(
                reference_x,
                x_data,
                rtol=0.0,
                atol=1e-8,
            ):
                raise RuntimeError("Wavelength axes changed between dark frames.")

            frames.append(dark)

        if reference_x is None:
            raise RuntimeError("No dark frames were acquired.")

        return reference_x, self._combine_frames(np.stack(frames), mode)
