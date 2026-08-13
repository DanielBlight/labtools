import asyncio

import numpy as np
from loguru import logger

from horiba_sdk.core.stitching import LinearSpectraStitch


async def get_range_spectrum(
    spec,
    start_wavelength,
    end_wavelength,
    stitch_pixel_overlap=20,
    background_subtract=False,
    n_frames=1,
    mode="single",
    dark_frame_mode="per_frame",
):
    """Acquire a stitched spectrum over a wavelength range.

    Steps through the centre wavelengths required to cover
    [start_wavelength, end_wavelength], acquires a frame at each position
    using :class:`~labtools.devices.horiba_spectrometer.HoribaSpectrometer`,
    then stitches and filters the result to the requested range.

    Parameters
    ----------
    spec : HoribaSpectrometer
        Connected and configured spectrometer instance.
    start_wavelength : float
        Start of the output wavelength range (nm).
    end_wavelength : float
        End of the output wavelength range (nm).
    stitch_pixel_overlap : int
        Pixel overlap between adjacent captures for stitching (default: 20).
    background_subtract : bool
        If True, subtract a dark spectrum using the selected dark timing mode.
    n_frames : int
        Number of frames per wavelength step, passed to
        :meth:`~HoribaSpectrometer.get_spectrum` (default: 1).
    mode : str
        Frame combination mode passed to
        :meth:`~HoribaSpectrometer.get_spectrum`:
        ``"single"``, ``"median"``, or ``"sigma_clip"``.
    dark_frame_mode : str
        Dark subtraction timing when ``background_subtract`` is enabled.
        ``"single"`` acquires one dark frame at the start of the full scan,
        while ``"per_frame"`` acquires a dark frame for each repeated signal
        acquisition before subtracting it.

    Returns
    -------
    x_values : numpy.ndarray
        Wavelength axis (nm), trimmed to [start_wavelength, end_wavelength].
    y_values : numpy.ndarray
        Intensity values.
    """
    if background_subtract and dark_frame_mode not in {"single", "per_frame"}:
        raise ValueError(f"dark_frame_mode must be 'single' or 'per_frame' when background_subtract is True, got {dark_frame_mode!r}")

    static_dark = None
    if background_subtract and dark_frame_mode == "single":
        _, static_dark = await _acquire_dark(spec)

    center_wavelengths = await spec.ccd.range_mode_center_wavelengths(
        spec.mono.id(), start_wavelength, end_wavelength, stitch_pixel_overlap
    )
    logger.info(f"Range scan: {len(center_wavelengths)} captures required.")

    captures = []
    for i, center_wavelength in enumerate(center_wavelengths):
        await spec.set_wavelength(center_wavelength)

        # Double-move on first step — ensures mono settles from rest
        if i == 0:
            await spec.set_wavelength(center_wavelength)

        frame_dark_mode = "none"
        if background_subtract:
            frame_dark_mode = "none" if static_dark is not None else dark_frame_mode

        x_data, y_data = await spec.get_spectrum(
            n_frames=n_frames,
            mode=mode,
            dark_frame_mode=frame_dark_mode,
        )

        if background_subtract and static_dark is not None:
            y_data = y_data - static_dark

        # LinearSpectraStitch expects [x_values, [y_values]]
        captures.append([list(x_data), [list(y_data)]])

    stitch = LinearSpectraStitch(captures)
    spectrum = stitch.stitched_spectra()

    # stitched_spectra() returns [x_values, [y_values]] — unwrap y before filtering
    x_out, y_out = _filter_range(spectrum[0], spectrum[1][0], start_wavelength, end_wavelength)
    return np.asarray(x_out), np.asarray(y_out)


async def _acquire_dark(spec):
    """Acquire a dark frame (shutter closed) using the CCD directly."""
    await spec.ccd.acquisition_start(open_shutter=False)
    await asyncio.sleep(spec._exposure_time + 0.005)
    while await spec.ccd.get_acquisition_busy():
        await asyncio.sleep(0.002)
    raw = await spec.ccd.get_acquisition_data()
    x_data = raw['acquisition'][0]['roi'][0]['xData']
    y_data = raw['acquisition'][0]['roi'][0]['yData'][0]
    return x_data, np.array(y_data)


def _filter_range(wavelengths, intensities, start, end):
    pairs = [(wl, i) for wl, i in zip(wavelengths, intensities) if start <= wl <= end]
    if not pairs:
        return [], []
    wls, ints = zip(*pairs)
    return list(wls), list(ints)
