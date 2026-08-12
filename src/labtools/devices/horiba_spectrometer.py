import asyncio

import numpy as np
from loguru import logger

from horiba_sdk.core.acquisition_format import AcquisitionFormat
from horiba_sdk.core.timer_resolution import TimerResolution
from horiba_sdk.core.x_axis_conversion_type import XAxisConversionType
from horiba_sdk.devices.device_manager import DeviceManager
from horiba_sdk.devices.single_devices.monochromator import Monochromator

# CCD indices in device_manager.charge_coupled_devices
CCD_SYMPHONY = 0
CCD_SYNCERITY = 1


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

    PRESETS = {
        "syncerity": {
            "ccd_index":       CCD_SYNCERITY,
            "grating":         Monochromator.Grating.SECOND,
            "mirror_position": "AXIAL",
            "roi":             {},
        },
        "symphony": {
            "ccd_index":       CCD_SYMPHONY,
            "grating":         Monochromator.Grating.THIRD,
            "mirror_position": "LATERAL",
            "roi":             {"x_size": 512, "x_bin": 1, "y_origin": 0, "y_size": 1, "y_bin": 1},
        },
    }

    def __init__(self, preset="syncerity", ccd_index=None):
        if preset is not None and preset not in self.PRESETS:
            raise ValueError(f"Unknown preset {preset!r}. Choose 'syncerity' or 'symphony'.")
        self._preset_name = preset
        self._preset = self.PRESETS[preset] if preset else {}
        self._ccd_index = ccd_index if ccd_index is not None else self._preset.get("ccd_index", CCD_SYNCERITY)
        self._device_manager = None
        self._exposure_time = None
        self.mono = None
        self.ccd = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self):
        """Start ICL, open mono and CCD. Raises RuntimeError if not found."""
        self._device_manager = DeviceManager(start_icl=True)
        await self._device_manager.start()

        if not self._device_manager.monochromators or not self._device_manager.charge_coupled_devices:
            await self._device_manager.stop()
            raise RuntimeError("Required monochromator or CCD not found.")

        self.mono = self._device_manager.monochromators[0]
        await self.mono.open()
        await self._wait_for_mono()

        self.ccd = self._device_manager.charge_coupled_devices[self._ccd_index]
        await self.ccd.open()
        await self._wait_for_ccd()

    async def disconnect(self):
        """Close devices and stop ICL."""
        try:
            if self.ccd is not None:
                await self.ccd.close()
            if self.mono is not None:
                await asyncio.sleep(1)  # SDK examples recommend a brief wait before closing mono
                await self.mono.close()
        except Exception:
            logger.exception("Error closing devices — ICL may not have stopped cleanly.")
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
        gain=2,
        speed=0,
        initialize=False,
        exposure_time=None,
        roi=None,
    ):
        """Configure mono grating/mirror, CCD gain/speed, exposure, and ROI.

        Values default to the active preset and can be overridden individually.

        Parameters
        ----------
        grating : Monochromator.Grating or None
            Grating to select. Defaults to preset value.
        mirror_position : Monochromator.MirrorPosition or None
            Exit mirror position. Defaults to preset value.
        gain : int
            CCD gain token (0: high light, 1: best dynamic range, 2: high gain).
        speed : int
            CCD speed token (0: 45 kHz, 1: 1 MHz, 2: 1 MHz Ultra).
        initialize : bool
            Run monochromator initialisation routine first.
        exposure_time : float or None
            Exposure time in seconds. Skipped if None.
        roi : dict or None
            ROI keyword arguments passed to :meth:`set_roi`. Overrides preset
            ROI. Pass ``{}`` to use :meth:`set_roi` defaults explicitly.
        """
        # Resolve grating from preset if not explicitly given
        if grating is None:
            grating = self._preset.get("grating", Monochromator.Grating.SECOND)

        # Resolve mirror position from preset string > AXIAL fallback
        if mirror_position is None:
            mirror_name = self._preset.get("mirror_position", "AXIAL")
            mirror_position = getattr(self.mono.MirrorPosition, mirror_name)

        # Resolve ROI: explicit arg overrides preset
        if roi is None:
            roi = self._preset.get("roi", {})

        if initialize:
            await self.mono.initialize()
        await self._wait_for_mono()

        await self.mono.set_turret_grating(grating)
        await self._wait_for_mono()

        await self.mono.set_mirror_position(self.mono.Mirror.EXIT, mirror_position)
        await self._wait_for_mono()

        ccd_config = await self.ccd.get_configuration()
        logger.info(f"CCD configuration: {ccd_config}")

        center_wavelength = await self.mono.get_current_wavelength()
        await self.ccd.set_center_wavelength(self.mono.id(), center_wavelength)
        await self.ccd.set_x_axis_conversion_type(XAxisConversionType.FROM_ICL_SETTINGS_INI)
        await self.ccd.set_acquisition_count(1)
        await self.ccd.set_gain(gain)
        await self.ccd.set_speed(speed)
        await self.ccd.set_timer_resolution(TimerResolution.MILLISECONDS)
        await self.ccd.set_acquisition_format(1, AcquisitionFormat.SPECTRA)

        if exposure_time is not None:
            await self.set_exposure_time(exposure_time)

        await self.set_roi(**roi)

    async def set_wavelength(self, wavelength):
        """Move the monochromator to a centre wavelength (nm)."""
        await self.mono.move_to_target_wavelength(wavelength)
        await self._wait_for_mono()
        actual = await self.mono.get_current_wavelength()
        logger.info(f"Monochromator wavelength: {actual} nm")
        await self.ccd.set_center_wavelength(self.mono.id(), actual)
        await self.ccd.set_x_axis_conversion_type(XAxisConversionType.FROM_ICL_SETTINGS_INI)

    async def set_slit_width(self, width_mm):
        """Set entrance slit width in mm."""
        await self.mono.set_slit_position(self.mono.Slit.A, width_mm)

    async def set_exposure_time(self, exposure_time_s):
        """Set CCD exposure time.

        Parameters
        ----------
        exposure_time_s : float
            Exposure time in seconds.
        """
        self._exposure_time = exposure_time_s
        await self.ccd.set_exposure_time(int(exposure_time_s * 1000))

    async def set_roi(self, roi_index=1, x_origin=0, y_origin=0, x_size=1024, y_size=100, x_bin=1, y_bin=100):
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
            x_origin=x_origin, y_origin=y_origin,
            x_size=x_size, y_size=y_size,
            x_bin=x_bin, y_bin=y_bin,
        )

    async def reset(self):
        """Abort any stuck acquisition and restart the CCD."""
        while await self.ccd.get_acquisition_busy():
            await asyncio.sleep(0.3)
            await self.ccd.acquisition_abort()
        await self.ccd.restart()
        await asyncio.sleep(7)

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    async def get_spectrum(self, exposure_time=None, n_frames=1, mode="single", k_sigma=3.0):
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
            (default: 3.0). Cosmic rays typically exceed the mean by 100–1000×
            so this threshold is conservative.

        Returns
        -------
        x_data : list
            Wavelength axis.
        y_data : numpy.ndarray
            Combined intensity values.
        """
        if mode not in ("single", "median", "sigma_clip"):
            raise ValueError(f"mode must be 'single', 'median', or 'sigma_clip', got {mode!r}")
        if mode in ("median", "sigma_clip") and n_frames < 3:
            raise ValueError(f"n_frames must be >= 3 for mode={mode!r}.")

        if exposure_time is not None:
            await self.set_exposure_time(exposure_time)
        elif self._exposure_time is None:
            raise RuntimeError("No exposure time set. Pass exposure_time or call configure() first.")

        if not await self.ccd.get_acquisition_ready():
            raise RuntimeError("CCD not ready for acquisition.")

        if mode == "single":
            return await self._acquire_single()

        frames = []
        for _ in range(n_frames):
            x_data, y_data = await self._acquire_single()
            frames.append(y_data)

        stacked = np.stack(frames)  # shape (n_frames, n_pixels)

        if mode == "median":
            return x_data, np.median(stacked, axis=0)

        # sigma_clip: mask outliers per pixel, then average clean values
        mean = stacked.mean(axis=0)
        std = stacked.std(axis=0)
        mask = np.abs(stacked - mean) > k_sigma * std
        clean = np.where(mask, np.nan, stacked)
        return x_data, np.nanmean(clean, axis=0)

    async def _acquire_single(self):
        """Acquire one frame and return (x_data, y_data)."""
        await self.ccd.acquisition_start(open_shutter=True)
        await asyncio.sleep(self._exposure_time + 0.005)
        await self._wait_for_ccd(poll_interval=0.002)

        raw = await self.ccd.get_acquisition_data()
        x_data = raw['acquisition'][0]['roi'][0]['xData']
        y_data = raw['acquisition'][0]['roi'][0]['yData'][0]
        return x_data, np.array(y_data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _wait_for_ccd(self, poll_interval=0.1):
        while await self.ccd.get_acquisition_busy():
            await asyncio.sleep(poll_interval)
            logger.debug("CCD busy...")

    async def _wait_for_mono(self):
        while await self.mono.is_busy():
            await asyncio.sleep(0.1)
            logger.debug("Mono busy...")

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()
