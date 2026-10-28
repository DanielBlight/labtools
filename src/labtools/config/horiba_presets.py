"""Native-free detector option tokens; hardware discovery remains in the wrapper."""

from copy import deepcopy

_OPTIONS = {
    "syncerity": {
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
        "default_gain": 2,
        "default_speed": 0,
        "gains": (("High Dynamic Range", 1), ("High Sensitivity", 2)),
        "speeds": (("1.5 MHz", 1), ("500 kHz Wrap", 127), ("300 kHz", 0)),
        "minimum_exposure_s": 0.1,
    },
}


def detector_options(preset: str) -> dict:
    """Return detached preset controls without importing a vendor SDK."""
    try:
        return deepcopy(_OPTIONS[preset])
    except KeyError as exc:
        raise ValueError(f"Unknown detector preset: {preset!r}") from exc
