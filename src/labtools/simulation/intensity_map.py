"""Run synthetic maps only: python -m labtools.simulation.intensity_map."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=None
    )
    parser.add_argument("--points", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--stop-after", type=int)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    if (
        (args.points is not None and args.points < 2)
        or args.seed < 0
        or (args.stop_after is not None and args.stop_after < 1)
    ):
        parser.error("points >= 2, seed >= 0 and stop-after >= 1 are required")
    if args.gui:
        if args.resume is not None or args.stop_after is not None:
            parser.error("With --gui, use the window's Resume and Stop buttons instead.")
        import sys

        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import QApplication

        from labtools.gui.intensity_map_gui import IntensityMapWindow

        app = QApplication([sys.argv[0]])
        app.setFont(QFont("Segoe UI", 9))
        window = IntensityMapWindow(
            simulation_only=True,
            simulation_seed=args.seed,
            simulation_realtime=args.realtime,
        )
        if args.output is not None:
            window.output_root.setText(str(args.output))
        if args.points is not None:
            window.x_points.setValue(args.points)
            window.y_points.setValue(args.points)
        window.show()
        raise SystemExit(app.exec())
    from labtools.acquisition.intensity_map import (
        IntensityMapConfig,
        acquire_intensity_map,
        config_from_resume_directory,
    )

    points = args.points if args.points is not None else 15
    output = args.output if args.output is not None else Path.home() / "Labtools Simulation"
    if args.resume:
        config = config_from_resume_directory(args.resume)
        if config.backend != "simulation":
            parser.error("This runner refuses to resume real-hardware data")
        config = replace(
            config, simulation_realtime=args.realtime, simulation_fail_after_points=None
        )
    else:
        config = IntensityMapConfig(
            x_start_v=-1.0,
            x_stop_v=1.0,
            x_points=points,
            y_start_v=-1.0,
            y_stop_v=1.0,
            y_points=points,
            integration_time_s=0.02,
            settle_time_s=0.0,
            channels=(1, 2),
            channel_thresholds_v=(0.1, 0.1),
            channel_edges=("rising", "rising"),
            output_root=output,
            backend="simulation",
            simulation_seed=args.seed,
            simulation_realtime=args.realtime,
        )
    latest = [0]

    def progress(snapshot):
        latest[0] = snapshot.points_complete
        print(f"SYNTHETIC: {snapshot.points_complete}/{snapshot.total_points}")

    result = acquire_intensity_map(
        config,
        resume_directory=args.resume,
        progress_callback=progress,
        cancel_requested=lambda: (
            args.stop_after is not None and latest[0] >= args.stop_after
        ),
    )
    print("SYNTHETIC DATA ONLY:", result.output_directory)
    print("Complete:", result.complete)


if __name__ == "__main__":
    main()
