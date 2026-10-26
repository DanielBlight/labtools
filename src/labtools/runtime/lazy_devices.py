"""Lazy native device factories; no connection cache."""
class LazyITC4000:
    """Compatibility factory; no VISA import until a real connection is requested."""

    DEFAULT_ADDRESS = 'USB0::0x1313::0x804A::M00739898::INSTR'

    def __new__(cls, *args, **kwargs):
        from labtools.devices.itc4000 import ITC4000
        return ITC4000(*args, **kwargs)

