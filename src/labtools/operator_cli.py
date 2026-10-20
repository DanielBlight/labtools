"""Operator commands; validate/init/doctor do not connect to hardware."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from labtools.config.anneal_workspace import (
    initialise_workspace, load_profile, load_recipe, profile_path, validate_recipe,
)


def main():
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
    args = parser.parse_args()
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


def anneal_gui():
    from labtools.gui.laser_anneal_gui import main as launch
    launch()


def intensity_gui():
    from labtools.gui.intensity_map_gui import main as launch
    launch()


if __name__ == "__main__":
    main()
