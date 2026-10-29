from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import SpectrumRequest, acquire_spectrum

settings = SpectrumSettings(
    configuration_id="toy-scene-v1",
    preset="syncerity",
    exposure_s=0.065,
    gain=0,
    speed=0,
    slit_width_mm=0.1,
    start_nm=500,
    end_nm=600,
    backend="simulation",
)
measurement = acquire_spectrum(
    SpectrumRequest(settings), progress=lambda state: print(state)
)
print(
    "synthetic:",
    measurement.provenance.synthetic,
    "samples:",
    len(measurement.result.wavelength_nm),
)
