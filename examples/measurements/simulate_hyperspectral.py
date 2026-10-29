"""Run a small deterministic hyperspectral simulation through the public facade."""

from labtools.config.hyperspectral import HyperspectralConfig
from labtools.config.spectrum import SpectrumSettings
from labtools.measurements import HyperspectralRequest, acquire_hyperspectral_map

settings = SpectrumSettings(
    "example-hyperspectral-v1",
    "syncerity",
    0.1,
    2,
    0,
    0.5,
    500.0,
    600.0,
    backend="simulation",
)
config = HyperspectralConfig(
    "example-hyperspectral-v1", settings, 0.0, 0.1, 2, 0.0, 0.1, 2
)
measurement = acquire_hyperspectral_map(HyperspectralRequest(config))
print(
    measurement.result.status,
    measurement.result.intensity.shape,
    measurement.provenance.synthetic,
)
