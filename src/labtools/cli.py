"""Operator CLI with lazy GUI, simulation and hardware imports."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from labtools.config.anneal_workspace import (
    initialise_workspace, load_profile, load_recipe, profile_path, validate_recipe,
)
from labtools.launchers import GUI_MODULES, launch_gui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labtools")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create an editable operator workspace")
    init.add_argument("directory", type=Path)
    for name in ("validate", "anneal"):
        command = sub.add_parser(name)
        command.add_argument("recipe", type=Path)
        if name == "anneal":
            command.add_argument("--confirm-optical-path", action="store_true")
    sub.add_parser("doctor", help="Check configuration only; no device access")
    gui = sub.add_parser("gui", help="Launch a standalone tool window")
    gui.add_argument("tool", choices=tuple(GUI_MODULES))
    simulation = sub.add_parser("simulate", help="Run explicitly synthetic data tools")
    tools = simulation.add_subparsers(dest="simulation_tool", required=True)
    tools.add_parser("intensity-map", add_help=False)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    if args.command == "simulate":
        from labtools.simulation.intensity_map import main as simulate
        simulate(remaining)
        return
    if remaining:
        parser.error("unrecognized arguments: " + " ".join(remaining))
    if args.command == "gui":
        launch_gui(args.tool)
        return
    try:
        if args.command == "init":
            print(initialise_workspace(args.directory))
            return
        profile = load_profile()
        if args.command == "doctor":
            print(f"Profile: {profile_path()} ({profile.profile_id})")
            print("Configuration valid. No hardware was opened or tested.")
            return
        recipe = load_recipe(args.recipe)
        validate_recipe(recipe, profile)
        if args.command == "validate":
            print(json.dumps(asdict(recipe), indent=2))
            print("Recipe valid. No hardware was opened.")
            return
        if not args.confirm_optical_path:
            parser.error("Hardware execution requires --confirm-optical-path after physical checks")
        from labtools.config.anneal_workspace import build_config
        from labtools.acquisition.laser_anneal import run_laser_anneal
        print(run_laser_anneal(build_config(recipe, profile), status_callback=print))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
