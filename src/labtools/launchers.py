"""Lazy standalone GUI entry points. Importing this module opens no devices."""

from __future__ import annotations

from importlib import import_module
from types import MappingProxyType

GUI_MODULES = MappingProxyType(
    {
        "spectrum": "labtools.gui.spectrum_gui_horiba",
        "mirror": "labtools.gui.mirror_voltage_gui",
        "intensity-map": "labtools.gui.intensity_map_gui",
        "anneal": "labtools.gui.laser_anneal_gui",
        "hyperspectral": "labtools.gui.hyperspectral_gui",
    }
)


def launch_gui(tool: str) -> None:
    """Launch a standalone tool, not a shared instrument session."""
    try:
        module_name = GUI_MODULES[tool]
    except KeyError:
        raise ValueError(f"Unknown GUI: {tool!r}") from None
    import_module(module_name).main()


def spectrum_gui() -> None:
    launch_gui("spectrum")


def mirror_gui() -> None:
    launch_gui("mirror")


def intensity_gui() -> None:
    launch_gui("intensity-map")


def hyperspectral_gui() -> None:
    launch_gui("hyperspectral")


def anneal_gui() -> None:
    launch_gui("anneal")
