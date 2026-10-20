"""Editable runner. Defaults to validation; --run operates hardware."""
import argparse
from pathlib import Path
from labtools.config.anneal_workspace import load_profile, load_recipe, validate_recipe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", type=Path)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    profile = load_profile()
    recipe = load_recipe(args.recipe)
    validate_recipe(recipe, profile)
    print("Recipe valid")
    if args.run:
        answer = input("Optical path checked and ready to expose sample? Type RUN: ")
        if answer != "RUN":
            raise SystemExit("Cancelled")
        from labtools.config.anneal_workspace import build_config
        from labtools.acquisition.laser_anneal import run_laser_anneal
        run_laser_anneal(build_config(recipe, profile), status_callback=print)


if __name__ == "__main__":
    main()
