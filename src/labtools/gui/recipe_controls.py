"""Recipe controls for the existing anneal GUI; no automatic hardware actions."""

from dataclasses import replace
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QPushButton

from labtools.config.anneal_workspace import (
    AnnealRecipe,
    load_profile,
    load_recipe,
    recipe_from_config,
    save_recipe,
    validate_recipe,
)

NUMERIC = {
    "x_start_v": "x_start",
    "x_stop_v": "x_stop",
    "x_points": "x_points",
    "y_start_v": "y_start",
    "y_stop_v": "y_stop",
    "y_points": "y_points",
    "passes": "passes",
    "point_dwell_s": "dwell",
    "mirror_settle_s": "settle",
    "anneal_rotation_coordinate": "anneal_stage_coordinate",
    "return_rotation_coordinate": "return_stage_coordinate",
    "maximum_open_time_s": "max_open",
}
CHECKS = {
    "serpentine": "serpentine",
    "return_rotation_stage": "return_stage",
    "save_run_log": "save_log",
}


def _apply(window, recipe):
    validate_recipe(recipe, load_profile())
    widgets = [
        getattr(window, name)
        for name in (*NUMERIC.values(), *CHECKS.values(), "output_root")
    ]
    for key, name in NUMERIC.items():
        widget = getattr(window, name)
        value = getattr(recipe, key)
        if not widget.minimum() <= value <= widget.maximum():
            raise ValueError(f"{key} is outside this GUI's supported range")
    old_blocks = [widget.blockSignals(True) for widget in widgets]
    try:
        for key, name in NUMERIC.items():
            getattr(window, name).setValue(getattr(recipe, key))
        for key, name in CHECKS.items():
            getattr(window, name).setChecked(getattr(recipe, key))
        window.output_root.setText(recipe.output_root)
    finally:
        for widget, old in zip(widgets, old_blocks, strict=True):
            widget.blockSignals(old)
    window.confirm.setChecked(False)
    window._update_estimate()


def setup_recipe_controls(window):
    window._operator_recipe_path = None
    row = QHBoxLayout()

    def guarded(operation):
        try:
            if window._thread is not None:
                raise ValueError("Stop the anneal before changing or saving a recipe")
            operation()
        except (ValueError, OSError) as exc:
            QMessageBox.critical(window, "Recipe error", str(exc))

    def load():
        filename, _ = QFileDialog.getOpenFileName(
            window, "Load recipe", str(Path.home()), "JSON recipes (*.json)"
        )
        if filename:
            _apply(window, load_recipe(Path(filename)))
            window._operator_recipe_path = Path(filename)
            window.status.setText(f"Loaded recipe: {filename}")

    def save(as_new=False):
        path = None if as_new else window._operator_recipe_path
        if path is None:
            filename, _ = QFileDialog.getSaveFileName(
                window,
                "Save recipe",
                str(Path.home() / "anneal.json"),
                "JSON recipes (*.json)",
            )
            if not filename:
                return
            path = Path(filename)
            if path.suffix.lower() != ".json":
                path = path.with_suffix(".json")
        recipe = recipe_from_config(window._build_config())
        save_recipe(path, recipe)
        window._operator_recipe_path = path
        window.status.setText(f"Saved recipe: {path}")

    def reset():
        profile = load_profile()
        recipe = replace(
            AnnealRecipe(),
            output_root=str(Path.home() / "Labtools Experiments" / "data"),
            maximum_open_time_s=profile.maximum_open_time_s,
        )
        _apply(window, recipe)
        window._operator_recipe_path = None

    for label, operation in (
        ("Load recipe", load),
        ("Save recipe", save),
        ("Save recipe as", lambda: save(True)),
        ("Restore recipe defaults", reset),
    ):
        button = QPushButton(label)
        button.clicked.connect(lambda checked=False, op=operation: guarded(op))
        row.addWidget(button)
    window.centralWidget().layout().insertLayout(1, row)
    window.sc10_port.setReadOnly(True)
    window.sc10_port.setToolTip("Connection is set by the instrument profile")
    try:
        window.sc10_port.setText(load_profile().sc10_port)
    except (ValueError, OSError) as exc:
        window.status.setText(str(exc))
