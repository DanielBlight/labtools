"""Guarded intensity-map GUI update. Run from the labtools repository root.

Uses AST locations, not exact multiline matching. No hardware is opened.
--check compiles proposed changes without writing. Original bytes are backed up.
"""
from __future__ import annotations

import argparse
import ast
import textwrap
from datetime import datetime
from pathlib import Path

TARGET = Path("src/labtools/gui/intensity_map_gui.py")
MARKER = "_intensity_map_preferences_v1"

METHODS = r'''
def _intensity_map_preferences_v1(self) -> None:
    """Restore widget preferences without connecting or applying hardware settings."""
    from PyQt6.QtCore import QSettings

    self._map_preferences = QSettings("labtools", "IntensityMap")
    widgets = self._map_preference_widgets()
    blocked = [(widget, widget.blockSignals(True)) for widget in widgets.values()]
    try:
        for name, widget in widgets.items():
            key = "preferences_v1/" + name
            if not self._map_preferences.contains(key):
                continue
            try:
                if isinstance(widget, QCheckBox):
                    widget.setChecked(self._map_preferences.value(key, type=bool))
                elif isinstance(widget, QComboBox):
                    value = self._map_preferences.value(key, type=str)
                    if widget.findText(value) >= 0:
                        widget.setCurrentText(value)
                elif isinstance(widget, QLineEdit):
                    widget.setText(self._map_preferences.value(key, type=str))
                else:
                    value_type = int if isinstance(widget, QSpinBox) else float
                    value = self._map_preferences.value(key, type=value_type)
                    if np.isfinite(value) and widget.minimum() <= value <= widget.maximum():
                        widget.setValue(value)
            except (TypeError, ValueError, OverflowError):
                continue
    finally:
        for widget, previous in blocked:
            widget.blockSignals(previous)
    self._sync_second_channel_visibility()
    self._toggle_colour_limit_controls(self.custom_colour_limits.isChecked())
    self._update_estimate()
    # Connection/output states are deliberately not restored.


def _map_preference_widgets(self) -> dict:
    names = (
        "x_start", "x_stop", "x_points", "y_start", "y_stop", "y_points",
        "settle", "serpentine", "output_root", "save_results", "address",
        "integration", "channel_1", "threshold_1", "edge_1", "use_second",
        "channel_2", "threshold_2", "edge_2", "laser_address", "laser_current",
        "log_colour_scale", "custom_colour_limits", "colour_min", "colour_max",
    )
    return {name: getattr(self, name) for name in names}


def _save_map_preferences(self) -> None:
    """Save entered values only, never output/connection state."""
    for name, widget in self._map_preference_widgets().items():
        if isinstance(widget, QCheckBox):
            value = widget.isChecked()
        elif isinstance(widget, QComboBox):
            value = widget.currentText()
        elif isinstance(widget, QLineEdit):
            value = widget.text()
        else:
            widget.interpretText()
            value = widget.value()
        self._map_preferences.setValue("preferences_v1/" + name, value)
    self._map_preferences.sync()


def _map_display_extent(self, x_values, y_values) -> tuple:
    """Retain coordinate order so descending scans display the correct pixels."""
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if x.ndim != 1 or y.ndim != 1 or not x.size or not y.size:
        raise ValueError("Map coordinates must be nonempty one-dimensional arrays")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Map coordinates must be finite")
    def limits(values):
        first, last = float(values[0]), float(values[-1])
        if first == last:
            padding = max(1.0e-6, abs(first) * 1.0e-6)
            return first - padding, last + padding
        return first, last
    return (*limits(x), *limits(y))


def _set_map_display_geometry(self, x_values, y_values, shape, *, force=False) -> None:
    extent = self._map_display_extent(x_values, y_values)
    signature = (tuple(shape), extent)
    if force or getattr(self, "_map_display_signature", None) != signature:
        self.image.set_extent(extent)
        self.axes.set_xlim(extent[0], extent[1])
        self.axes.set_ylim(extent[2], extent[3])
        self.axes.set_xlabel("Mirror X voltage (V)")
        self.axes.set_ylabel("Mirror Y voltage (V)")
        self._map_display_signature = signature
        # Discard zoom history from the previous map, not on every frame.
        self.toolbar.update()
        self.toolbar.push_current()


def _reset_map_display(self, config) -> None:
    """Clear previous pixels and set new axes before starting the worker."""
    x = np.linspace(config.x_start_v, config.x_stop_v, config.x_points)
    y = np.linspace(config.y_start_v, config.y_stop_v, config.y_points)
    values = np.full((config.y_points, config.x_points), np.nan)
    self._latest_plot_values = values
    self.image.set_data(values)
    self._set_map_display_geometry(x, y, values.shape, force=True)
    self.axes.set_title("Starting acquisition")
    self.plot_meta.setText("Waiting for map data")
    self._refresh_colour_scale()
    self.canvas.draw_idle()
'''


def unique(nodes, name):
    found = [node for node in nodes if getattr(node, "name", None) == name]
    if len(found) != 1:
        raise ValueError(f"Expected one {name}; found {len(found)}. File unchanged.")
    return found[0]


def patch(source):
    tree = ast.parse(source)
    window = unique(tree.body, "IntensityMapWindow")
    if any(getattr(n, "name", None) == MARKER for n in window.body):
        raise ValueError("This update is already installed. Do not apply twice.")
    init = unique(window.body, "__init__")
    start = unique(window.body, "_start_worker")
    progress = unique(window.body, "_on_progress")
    close = unique(window.body, "closeEvent")
    # Require the known shape-only rebuild block rather than touching arbitrary ifs.
    candidates = [n for n in progress.body if isinstance(n, ast.If)
                  and "self.image.get_array().shape" in ast.unparse(n.test)
                  and "values.shape" in ast.unparse(n.test)]
    if len(candidates) != 1:
        raise ValueError("Could not identify the old plot shape check. File unchanged.")
    old = candidates[0]
    start_calls = [n for n in ast.walk(start) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and ast.unparse(n.func) == "self._thread.start"]
    if len(start_calls) != 1:
        raise ValueError("Could not identify worker start. File unchanged.")
    # Reset immediately before thread creation, after all existing validation.
    thread_assignments = [n for n in start.body if isinstance(n, ast.Assign)
                          and any(ast.unparse(t) == "self._thread" for t in n.targets)]
    if len(thread_assignments) != 1:
        raise ValueError("Could not identify thread creation. File unchanged.")
    close_calls = [n for n in close.body if isinstance(n, ast.Expr)
                   and isinstance(n.value, ast.Call)
                   and ast.unparse(n.value.func) == "super().closeEvent"]
    if len(close_calls) != 1:
        raise ValueError("Could not identify accepted close path. File unchanged.")
    replacement = (
        "        self.image.set_data(values)\n"
        "        self._set_map_display_geometry(\n"
        "            snapshot.x_values_v, snapshot.y_values_v, values.shape\n"
        "        )\n"
    )
    edits = [
        (old.lineno - 1, old.end_lineno, replacement),
        (init.end_lineno, init.end_lineno, "        self._intensity_map_preferences_v1()\n"),
        (thread_assignments[0].lineno - 1, thread_assignments[0].lineno - 1,
         "        self._reset_map_display(config)\n"),
        (close_calls[0].end_lineno, close_calls[0].end_lineno,
         "        if event.isAccepted():\n            self._save_map_preferences()\n"),
        (window.end_lineno, window.end_lineno, "\n" + textwrap.indent(textwrap.dedent(METHODS).strip(), "    ") + "\n"),
    ]
    lines = source.splitlines(keepends=True)
    for begin, end, text in sorted(edits, reverse=True):
        lines[begin:end] = [text]
    updated = "".join(lines)
    compile(updated, str(TARGET), "exec")
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    original = TARGET.read_bytes()
    updated = patch(original.decode("utf-8-sig"))
    if args.check:
        print("[OK] Proposed update compiles. No files changed or hardware opened.")
        return
    backup = TARGET.with_name(TARGET.name + ".before-axes-settings-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
    backup.write_bytes(original)
    try:
        TARGET.write_text(updated, encoding="utf-8")
        compile(TARGET.read_text(encoding="utf-8"), str(TARGET), "exec")
    except Exception:
        TARGET.write_bytes(original)
        raise
    print("[OK] Updated axes refresh and per-user settings.")
    print(f"Backup: {backup}")
    print("No hardware was opened. Test the GUI before removing the backup.")


if __name__ == "__main__":
    main()
