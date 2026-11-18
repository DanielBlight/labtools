"""Unified offline workspace entry and cooperative workflow lifecycle helpers.

No Qt/native imports until main launches the explicit simulation window.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def busy_workflows(pages):
    """Include worker teardown, not just acquisition completion."""
    busy = []
    for name, page in pages.items():
        if name == "Intensity map":
            active = page.map_controller.busy
        elif name == "Spectrum":
            active = page._spectrometer_busy or bool(page._async_tasks)
        else:
            raise ValueError(f"Unknown workspace workflow: {name}")
        if active:
            busy.append(name)
    return tuple(busy)


def stop_workflows(pages):
    """Attempt every active stop request even if another request fails."""
    errors = []
    for name in busy_workflows(pages):
        try:
            pages[name].request_stop()
        except Exception as error:  # noqa: BLE001 - independent GUI stop requests
            errors.append(f"{name}: {type(error).__name__}: {error}")
    return tuple(errors)


def close_workflows(pages):
    """Never close a page while either workflow still owns a worker."""
    if busy_workflows(pages):
        return False
    for page in pages.values():
        if not page.close():
            # An idle child may veto close; restore pages already hidden.
            for existing in pages.values():
                existing.show()
            return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unified simulation workspace; no hardware control")
    parser.add_argument("--output", type=Path, default=Path.home() / "Labtools Simulation")
    parser.add_argument("--config", type=Path, help="Explicit simulation resource configuration JSON")
    args = parser.parse_args(argv)
    from labtools.config.workspace import WorkspaceConfig, load_workspace_config

    try:
        config = load_workspace_config(args.config) if args.config else WorkspaceConfig()
        config.validate()
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    from PyQt6.QtWidgets import QApplication

    from labtools.gui.workspace import SimulationWorkspace

    app = QApplication([sys.argv[0]])
    window = SimulationWorkspace(output_root=args.output.expanduser(), config=config)
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
