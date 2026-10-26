"""Manual mirror backend factory; importing this module opens no hardware."""
import math

MIN_V = -10.0
MAX_V = 10.0
DIO_PIN = 2


def validate_target(x, y):
    if not all(math.isfinite(v) and MIN_V <= v <= MAX_V for v in (x, y)):
        raise ValueError("Target must be between -10 and +10 V")


def open_real_mirror():
    """Return (owned connection, mirror); send no movement on connection."""
    from labtools.devices.labjack_u6 import LabJackU6
    from labtools.devices.scanning_mirror import ScanningMirror
    device = LabJackU6()
    try:
        return device, ScanningMirror(device, dio_pin=DIO_PIN)
    except BaseException as exc:
        try:
            device.close()
        except Exception as close_error:
            exc.add_note(f"Mirror connection cleanup failed: {close_error!r}")
        raise
