"""Compatibility entry points; implementation now lives in labtools.cli."""
from labtools.cli import main
from labtools.launchers import anneal_gui, intensity_gui, mirror_gui, spectrum_gui
__all__ = ["main", "anneal_gui", "intensity_gui", "mirror_gui", "spectrum_gui"]

if __name__ == "__main__":
    main()
