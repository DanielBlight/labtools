"""Run the existing simulation workspace with resource-specific injected services."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from labtools.config.workspace import WorkspaceConfig, load_workspace_config
from labtools.simulation.workspace_services import InjectedSimulationServices


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path.home() / "Labtools Simulation")
    args = parser.parse_args(argv)
    try:
        config = load_workspace_config(args.config) if args.config else WorkspaceConfig()
        config.validate()
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    from PyQt6.QtWidgets import QApplication

    from labtools.gui.workspace import SimulationWorkspace

    services = InjectedSimulationServices()
    app = QApplication([sys.argv[0]])
    window = SimulationWorkspace(
        output_root=args.output, config=config,
        map_acquisition=services.acquire_map, spectrum_service=services.spectrum,
    )
    services.bind(window.ownership)
    window.show()
    code = app.exec()
    # Diagnostics only; not acceptance or a new persistent resource registry.
    print(json.dumps({"simulation_service_events": services.events()}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
