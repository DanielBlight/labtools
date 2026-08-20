from __future__ import annotations

import asyncio
from typing import ClassVar, Literal, Self

import numpy as np
from horiba_sdk.core.acquisition_format import AcquisitionFormat
from horiba_sdk.core.timer_resolution import TimerResolution
from horiba_sdk.core.x_axis_conversion_type import XAxisConversionType
from horiba_sdk.devices.device_manager import DeviceManager
from horiba_sdk.devices.single_devices.monochromator import Monochromator
from loguru import logger

# CCD indices in device_manager.charge_coupled_devices
CCD_SYMPHONY = 0
CCD_SYNCERITY = 1

# Public type alias imported by range_spectrum.py.
CombineMode = Literal["single", "mean", "median", "sigma_clip"]


class HoribaSpectrometer:
    """Async wrapper for a Horiba monochromator + CCD system.

    Manages connection lifetime and provides a clean API for common
    spectroscopy operations. Use as an async context manager::

        async with HoribaSpectrometer(preset="syncerity") as spec:
            await spec.configure()
            await spec.set_wavelength(785)
            x, y = await spec.get_spectrum(exposure_time=0.5)

    Two named presets are available: ``"syncerity"`` (default) and
    ``"symphony"``. Individual kwargs passed to :meth:`configure` always
    override the preset.

    Parameters
    ----------
    preset : str or None
        ``"syncerity"`` or ``"symphony"``. Sets the CCD index, grating,
        mirror position and ROI defaults. Ignored if ``None``.
    ccd_index : int or None
        Override the CCD index. Inferred from ``preset`` if not given.
    """

    PRESETS: ClassVar[dict[str, dict[str, object]]] = {
        "syncerity": {
            "ccd_index": CCD_SYNCERITY,
            "expected_device_type": "HORIBA Syncerity",
            "expected_chip_width": 1024,
            "expected_chip_height": 256,
            "expected_serial_number": "Camera SN: 926",
            "grating": Monochromator.Grating.SECOND,
            "mirror_position": Monochromator.MirrorPosition.AXIAL,
            "roi": {
                "x_size": 1024,
                "x_bin": 1,
                "y_origin": 0,
                "y_size": 256,
                "y_bin": 256,
            },
            "default_gain": 2,
            "default_speed": 0,
            "gains": (
                ("Best Dynamic Range", 1),
                ("High Sensitivity", 2),
                ("High Light", 0),
            ),
            "speeds": (
                ("1 MHz", 1),
                ("1 MHz Ultra", 2),
                ("500 kHz Wrap", 127),
                ("45 kHz", 0),
            ),
            "minimum_exposure_s": 0.065,
        },
        "symphony": {
            "ccd_index": CCD_SYMPHONY,
            "expected_device_type": "HORIBA Synapse / Symphony II",
            "expected_chip_width": 512,
            "expected_chip_height": 1,
            "expected_serial_number": "Camera SN: 26070",
            "grating": Monochromator.Grating.THIRD,
            "mirror_position": Monochromator.MirrorPosition.LATERAL,
            "roi": {
                "x_size": 512,
                "x_bin": 1,
                "y_origin": 0,
                "y_size": 1,
                "y_bin": 1,
            },
            "default_gain": 2,
            "default_speed": 0,
            "gains": (
                ("High Dynamic Range", 1),
                ("High Sensitivity", 2),
            ),
            "speeds": (
                ("1.5 MHz", 1),
                ("500 kHz Wrap", 127),
                ("300 kHz", 0),
            ),
            # No detector-specific continuous shutter minimum was supplied.
            # Use the same conservative GUI floor as the Syncerity.
            "minimum_exposure_s": 0.100,
        },
    }

    @classmethod
    def preset_options(cls, preset: str) -> dict:
        """Return a copy of the user-selectable settings for one preset."""
        if preset not in cls.PRESETS:
            raise ValueError(f"Unknown preset {preset!r}.")
        selected = cls.PRESETS[preset]
        return {
            "gains": tuple(selected["gains"]),
            "speeds": tuple(selected["speeds"]),
            "default_gain": int(selected["default_gain"]),
            "default_speed": int(selected["default_speed"]),
            "minimum_exposure_s": float(selected["minimum_exposure_s"]),
        }

    def __init__(self, preset: str | None = "syncerity", ccd_index: int | None = None):
        if preset is not None and preset not in self.PRESETS:
            raise ValueError(
                f"Unknown preset {preset!r}. Choose 'syncerity' or 'symphony'."
            )
        self._preset_name = preset
        self._preset = self.PRESETS[preset] if preset else {}
        self._ccd_index = (
            ccd_index
            if ccd_index is not None
            else self._preset.get("ccd_index", CCD_SYNCERITY)
        )
        self._device_manager = None
        self._exposure_time = None
        self.mono = None
        self.ccd = None
        self._ccd_configuration: dict | None = None
        self._active_gain: int | None = None
        self._active_speed: int | None = None
        self._active_grating = None
        self._active_mirror = None
        self._active_slit_width_mm: float | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start ICL, open the monochromator and verify the selected detector."""
        self._device_manager = DeviceManager(start_icl=True)
        await self._device_manager.start()

        try:
            monos = list(self._device_manager.monochromators)
            ccds = list(self._device_manager.charge_coupled_devices)

            if not monos or not ccds:
                raise RuntimeError("Required monochromator or CCD not found.")
            if self._ccd_index >= len(ccds):
                raise RuntimeError(
                    f"Preset {self._preset_name!r} requests CCD index "
                    f"{self._ccd_index}, but only {len(ccds)} detector(s) were found."
                )

            self.mono = monos[0]
            await self.mono.open()
            await self._wait_for_mono()

            self.ccd = ccds[self._ccd_index]
            await self.ccd.open()
            await self._wait_for_ccd()

            self._ccd_configuration = await self.ccd.get_configuration()
            self._verify_detector_identity(self._ccd_configuration)

        except Exception:
            await self.disconnect()
            raise

    def _verify_detector_identity(self, configuration: dict) -> None:
        """Stop before optical movement if the selected CCD is not the preset CCD."""
        if not self._preset:
            return

        def normalise_text(value: object) -> str:
            """Normalise SDK text fields that may contain extra whitespace."""
            return " ".join(str(value).replace("\x00", "").split())

        checks = {
            "device type": (
                normalise_text(configuration.get("deviceType", "")),
                normalise_text(self._preset["expected_device_type"]),
            ),
            "chip width": (
                int(configuration.get("chipWidth", -1)),
                int(self._preset["expected_chip_width"]),
            ),
            "chip height": (
                int(configuration.get("chipHeight", -1)),
                int(self._preset["expected_chip_height"]),
            ),
            "serial number": (
                normalise_text(configuration.get("serialNumber", "")),
                normalise_text(self._preset["expected_serial_number"]),
            ),
        }
        mismatches = [
            f"{name}: expected {expected!r}, reported {reported!r}"
            for name, (reported, expected) in checks.items()
            if reported != expected
        ]
        if mismatches:
            raise RuntimeError(
                f"Detector does not match preset {self._preset_name!r}: "
                + "; ".join(mismatches)
            )

    async def disconnect(self) -> None:
        """Close devices and stop ICL."""
        try:
            if self.ccd is not None:
                await self.ccd.close()
            if self.mono is not None:
                await asyncio.sleep(
                    1
                )  # SDK examples recommend a brief wait before closing mono
                await self.mono.close()
        except Exception:  # noqa: BLE001
            logger.exception(
                "Error closing devices — ICL may not have stopped cleanly."
            )
        finally:
            if self._device_manager is not None:
                await self._device_manager.stop()

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    async def configure(
        self,
        grating=None,
        mirror_position=None,
        gain: int | None = None,
        speed: int | None = None,
        initialize: bool = False,
        exposure_time: float | None = None,
        roi: dict | None = None,
        entrance_slit_width_mm: float | None = None,
    ) -> None:
        """Apply and verify the selected optical and detector configuration.

        Values default to the active preset. Hardware is moved only when its
        current readback differs from the requested preset value.
        """
        if self.mono is None or self.ccd is None:
            raise RuntimeError("Connect the HORIBA system before configuration.")

        if grating is None:
            grating = self._preset.get("grating")
        if mirror_position is None:
            mirror_position = self._preset.get("mirror_position")
        if gain is None:
            gain = int(self._preset.get("default_gain", 0))
        if speed is None:
            speed = int(self._preset.get("default_speed", 0))
        if roi is None:
            roi = dict(self._preset.get("roi", {}))

        if initialize:
            await self.mono.initialize()
            await self._wait_for_mono()

        configuration = self._ccd_configuration or await self.ccd.get_configuration()
        self._verify_detector_identity(configuration)
        self._validate_detector_token(configuration, "gains", gain, "gain")
        self._validate_detector_token(configuration, "speeds", speed, "speed")

        if exposure_time is not None:
            minimum = float(self._preset.get("minimum_exposure_s", 0.0))
            if exposure_time < minimum:
                raise ValueError(
                    f"Preset {self._preset_name!r} requires an exposure of at "
                    f"least {minimum:.3f} s for the configured continuous "
                    "SDrive shutter workflow."
                )

        if grating is not None:
            current_grating = await self.mono.get_turret_grating()
            if current_grating != grating:
                logger.info(
                    "Moving grating from {} to {}",
                    current_grating.name,
                    grating.name,
                )
                await self.mono.set_turret_grating(grating)
                await asyncio.sleep(0.5)
                await self._wait_for_mono()
            reported_grating = await self.mono.get_turret_grating()
            if reported_grating != grating:
                raise RuntimeError(
                    f"Grating readback mismatch: expected {grating.name}, "
                    f"reported {reported_grating.name}."
                )
            self._active_grating = reported_grating

        if mirror_position is not None:
            current_mirror = await self.mono.get_mirror_position(self.mono.Mirror.EXIT)
            if current_mirror != mirror_position:
                logger.info(
                    "Moving exit mirror from {} to {}",
                    current_mirror.name,
                    mirror_position.name,
                )
                await self.mono.set_mirror_position(
                    self.mono.Mirror.EXIT,
                    mirror_position,
                )
                await asyncio.sleep(0.5)
                await self._wait_for_mono()
            reported_mirror = await self.mono.get_mirror_position(self.mono.Mirror.EXIT)
            if reported_mirror != mirror_position:
                raise RuntimeError(
                    f"Exit mirror readback mismatch: expected {mirror_position.name}, "
                    f"reported {reported_mirror.name}."
                )
            self._active_mirror = reported_mirror

        if entrance_slit_width_mm is not None:
            self._active_slit_width_mm = await self.set_slit_width(
                entrance_slit_width_mm
            )

        center_wavelength = await self.mono.get_current_wavelength()
        await self.ccd.set_center_wavelength(self.mono.id(), center_wavelength)
        await self.ccd.set_x_axis_conversion_type(
            XAxisConversionType.FROM_ICL_SETTINGS_INI
        )
        await self.ccd.set_acquisition_count(1)
        await self.ccd.set_gain(int(gain))
        await self.ccd.set_speed(int(speed))
        await self.ccd.set_timer_resolution(TimerResolution.MILLISECONDS)
        await self.ccd.set_acquisition_format(1, AcquisitionFormat.SPECTRA_IMAGE)

        self._active_gain = int(gain)
        self._active_speed = int(speed)

        if exposure_time is not None:
            await self.set_exposure_time(exposure_time)

        await self.set_roi(**roi)

        logger.info("Verified HORIBA configuration: {}", self.configuration_summary())

    @staticmethod
    def _validate_detector_token(
        configuration: dict,
        field: str,
        token: int,
        label: str,
    ) -> None:
        available = {
            int(item["token"]): str(item["info"])
            for item in configuration.get(field, [])
        }
        if int(token) not in available:
            raise ValueError(
                f"Unsupported {label} token {token}; available values are {available}."
            )

    def configuration_summary(self) -> str:
        """Return a concise summary of the verified active configuration."""
        detector = "unknown"
        if self._ccd_configuration:
            detector = str(self._ccd_configuration.get("deviceType", "unknown"))
        grating = getattr(self._active_grating, "name", "not checked")
        mirror = getattr(self._active_mirror, "name", "not checked")
        slit = (
            "not set"
            if self._active_slit_width_mm is None
            else f"{self._active_slit_width_mm:.3f} mm"
        )
        return (
            f"{detector}; grating {grating}; exit mirror {mirror}; "
            f"entrance slit {slit}; gain token {self._active_gain}; "
            f"speed token {self._active_speed}"
        )

    async def prepare_wavelength_axis(self) -> float:
        """Initialise the calibrated CCD wavelength axis at the current centre.

        Range-mode centre calculations require the monochromator identity,
        current wavelength and CCD x-axis conversion to be established first.
        """
        if self.mono is None or self.ccd is None:
            raise RuntimeError(
                "Connect and configure the HORIBA system before preparing "
                "the wavelength axis."
            )

        await self._wait_for_mono()
        current_wavelength = float(await self.mono.get_current_wavelength())
        await self.ccd.set_center_wavelength(
            self.mono.id(),
            current_wavelength,
        )
        await self.ccd.set_x_axis_conversion_type(
            XAxisConversionType.FROM_ICL_SETTINGS_INI
        )
        logger.debug(
            "Prepared calibrated wavelength axis at {:.3f} nm",
            current_wavelength,
        )
        return current_wavelength

    async def set_wavelength(self, wavelength: float) -> float:
        """Move to a centre wavelength and return the verified readback in nm."""
        await self.mono.move_to_target_wavelength(float(wavelength))
        await self._wait_for_mono()
        actual = float(await self.mono.get_current_wavelength())
        logger.info("Monochromator wavelength: {:.3f} nm", actual)
        await self.ccd.set_center_wavelength(self.mono.id(), actual)
        await self.ccd.set_x_axis_conversion_type(
            XAxisConversionType.FROM_ICL_SETTINGS_INI
        )
        return actual

    async def set_slit_width(self, width_mm: float) -> float:
        """Set and verify entrance Slit A width in millimetres."""
        width_mm = float(width_mm)
        if width_mm <= 0:
            raise ValueError("Entrance slit width must be greater than zero.")

        slit = self.mono.Slit.A
        current = float(await self.mono.get_slit_position_in_mm(slit))
        if not np.isclose(current, width_mm, rtol=0.0, atol=0.005):
            await self.mono.set_slit_position(slit, width_mm)
            await asyncio.sleep(0.5)
            await self._wait_for_mono()

        reported = float(await self.mono.get_slit_position_in_mm(slit))
        if not np.isclose(reported, width_mm, rtol=0.0, atol=0.005):
            raise RuntimeError(
                f"Entrance slit readback mismatch: requested {width_mm:.3f} mm, "
                f"reported {reported:.3f} mm."
            )
        logger.info(
            "Entrance slit requested at {:.3f} mm, reported {:.3f} mm",
            width_mm,
            reported,
        )
        return reported

    async def set_exposure_time(self, exposure_time_s: float) -> None:
        """Set CCD exposure time.

        Parameters
        ----------
        exposure_time_s : float
            Exposure time in seconds.
        """
        self._exposure_time = exposure_time_s
        await self.ccd.set_exposure_time(int(exposure_time_s * 1000))

    async def set_roi(
        self,
        roi_index: int = 1,
        x_origin: int = 0,
        y_origin: int = 0,
        x_size: int = 1024,
        y_size: int = 100,
        x_bin: int = 1,
        y_bin: int = 100,
    ) -> None:
        """Set the CCD region of interest.

        Parameters
        ----------
        roi_index : int
            One-based ROI index (default: 1).
        x_origin, y_origin : int
            Top-left corner of the ROI in pixels.
        x_size, y_size : int
            Width and height of the ROI in pixels.
        x_bin, y_bin : int
            Binning factors.
        """
        await self.ccd.set_region_of_interest(
            roi_index=roi_index,
            x_origin=x_origin,
            y_origin=y_origin,
            x_size=x_size,
            y_size=y_size,
            x_bin=x_bin,
            y_bin=y_bin,
        )

    async def reset(self) -> None:
        """Abort any stuck acquisition and restart the CCD."""
        while await self.ccd.get_acquisition_busy():
            await asyncio.sleep(0.3)
            await self.ccd.acquisition_abort()
        await self.ccd.restart()
        await asyncio.sleep(7)

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    async def get_spectrum(
        self,
        exposure_time: float | None = None,
        n_frames: int = 1,
        mode: str = "single",
        k_sigma: float = 3.0,
        dark_frame_mode: str = "none",
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire a spectrum from the CCD.

        Parameters
        ----------
        exposure_time : float or None
            Exposure time in seconds. If None, uses the value from the last
            call to :meth:`set_exposure_time` or :meth:`configure`.
        n_frames : int
            Number of frames to acquire (default: 1). Ignored when
            ``mode="single"``.
        mode : str
            How to combine frames when ``n_frames > 1``:

            ``"single"``
                One frame, no combining. Fast; no cosmic ray protection.
            ``"median"``
                Per-pixel median of ``n_frames`` frames. Simple cosmic ray
                rejection. Requires ``n_frames >= 3``.
            ``"sigma_clip"``
                Per-pixel mean after discarding values more than ``k_sigma``
                standard deviations from the mean. Better SNR than median
                because clean frames are averaged rather than selected.
                Requires ``n_frames >= 3``.
        k_sigma : float
            Clipping threshold in standard deviations for ``mode="sigma_clip"``
            (default: 3.0).
        dark_frame_mode : str
            Dark subtraction timing. ``"none"`` disables subtraction,
            ``"single"`` subtracts one dark frame captured at the start of the
            acquisition, and ``"per_frame"`` captures a dark frame for each
            repeated signal frame before subtracting it.

        Returns
        -------
        x_data : list
            Wavelength axis.
        y_data : numpy.ndarray
            Combined intensity values.
        """
        if mode not in ("single", "mean", "median", "sigma_clip"):
            raise ValueError(
                "mode must be 'single', 'mean', 'median', or "
                f"'sigma_clip', got {mode!r}"
            )
        if dark_frame_mode == "once":
            dark_frame_mode = "single"
        if dark_frame_mode not in ("none", "single", "per_frame"):
            raise ValueError(
                "dark_frame_mode must be 'none', 'once', 'single', or "
                f"'per_frame', got {dark_frame_mode!r}"
            )
        if mode == "single" and n_frames != 1:
            raise ValueError("n_frames must be 1 for mode='single'.")
        if mode in ("median", "sigma_clip") and n_frames < 3:
            raise ValueError(f"n_frames must be >= 3 for mode={mode!r}.")

        if exposure_time is not None:
            await self.set_exposure_time(exposure_time)
        elif self._exposure_time is None:
            raise RuntimeError(
                "No exposure time set. Pass exposure_time or call configure() first."
            )

        if not await self.ccd.get_acquisition_ready():
            raise RuntimeError("CCD not ready for acquisition.")

        if dark_frame_mode == "single":
            _, dark = await self._acquire_single(open_shutter=False)

        frames = []
        for _ in range(n_frames):
            if dark_frame_mode == "per_frame":
                _, dark = await self._acquire_single(open_shutter=False)
            x_data, y_data = await self._acquire_single(open_shutter=True)
            if dark_frame_mode in {"single", "per_frame"}:
                y_data = y_data - dark
            frames.append(y_data)

        if mode == "single":
            return x_data, frames[0]

        stacked = np.stack(frames)  # shape (n_frames, n_pixels)

        if mode == "mean":
            return x_data, np.mean(stacked, axis=0)

        if mode == "median":
            return x_data, np.median(stacked, axis=0)

        # sigma_clip: mask outliers per pixel, then average clean values
        mean = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        mask = np.abs(stacked - mean) > k_sigma * std
        clean = np.where(mask, np.nan, stacked)
        return x_data, np.nanmean(clean, axis=0)

    async def get_dark_spectrum(
        self,
        *,
        n_frames: int = 1,
        mode: CombineMode = "single",
        k_sigma: float = 3.0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire and combine closed-shutter frames at the current centre."""
        if mode not in ("single", "mean", "median", "sigma_clip"):
            raise ValueError(f"Unsupported dark-frame combination mode {mode!r}.")
        if mode == "single" and n_frames != 1:
            raise ValueError("n_frames must be 1 for mode='single'.")
        if mode in ("median", "sigma_clip") and n_frames < 3:
            raise ValueError(f"n_frames must be >= 3 for mode={mode!r}.")
        if n_frames < 1:
            raise ValueError("n_frames must be at least 1.")
        if self._exposure_time is None:
            raise RuntimeError("Configure the exposure time before acquiring a dark.")

        frames: list[np.ndarray] = []
        x_data = np.empty(0, dtype=float)
        for _ in range(n_frames):
            x_data, y_data = await self._acquire_single(open_shutter=False)
            frames.append(y_data)

        if mode == "single":
            return x_data, frames[0]

        stacked = np.stack(frames)
        if mode == "mean":
            return x_data, np.mean(stacked, axis=0)
        if mode == "median":
            return x_data, np.median(stacked, axis=0)

        mean = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        mask = np.abs(stacked - mean) > k_sigma * std
        clean = np.where(mask, np.nan, stacked)
        return x_data, np.nanmean(clean, axis=0)

    async def _acquire_single(
        self,
        open_shutter: bool = True,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Acquire one frame and return matching NumPy arrays."""
        await self.ccd.acquisition_start(open_shutter=open_shutter)
        await asyncio.sleep(self._exposure_time + 0.005)
        await self._wait_for_ccd(poll_interval=0.002)

        raw = await self.ccd.get_acquisition_data()
        roi = raw["acquisition"][0]["roi"][0]
        x_data = np.asarray(roi["xData"], dtype=float)
        y_data = np.asarray(roi["yData"][0], dtype=float)

        if x_data.ndim != 1 or y_data.ndim != 1:
            raise RuntimeError(
                "Expected one-dimensional HORIBA spectrum arrays; "
                f"received x={x_data.shape}, y={y_data.shape}."
            )
        if x_data.shape != y_data.shape:
            raise RuntimeError(
                "HORIBA wavelength and intensity arrays have different shapes: "
                f"x={x_data.shape}, y={y_data.shape}."
            )
        if not np.all(np.isfinite(x_data)) or not np.all(np.isfinite(y_data)):
            raise RuntimeError("HORIBA acquisition returned non-finite values.")

        return x_data, y_data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _wait_for_ccd(self, poll_interval: float = 0.1) -> None:
        while await self.ccd.get_acquisition_busy():
            await asyncio.sleep(poll_interval)
            logger.debug("CCD busy...")

    async def _wait_for_mono(self) -> None:
        while await self.mono.is_busy():
            await asyncio.sleep(0.1)
            logger.debug("Mono busy...")

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, *_) -> None:
        await self.disconnect()
