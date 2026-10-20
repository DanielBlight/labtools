"""Install operator recipes and profile validation without opening hardware.

AST-based edits tolerate Ruff formatting and Windows line endings. Run --check
first. Original files and hashes are saved in .labtools-migrations. --rollback
refuses to overwrite files modified since installation.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

PAYLOAD = {'src/labtools/config/__init__.py': '"""Operator recipes and maintainer-owned instrument profiles."""\n', 'src/labtools/config/anneal_workspace.py': '"""Strict JSON recipes, instrument profiles and anneal policy validation.\n\nNo hardware is imported until build_config is called. Validation and workspace\ncreation never connect to devices. Filesystem permissions protect the profile;\nthis module is not a security boundary against arbitrary Python execution.\n"""\nfrom __future__ import annotations\n\nimport hashlib\nimport json\nimport math\nimport os\nfrom dataclasses import asdict, dataclass, fields, replace\nfrom importlib.metadata import PackageNotFoundError, version\nfrom pathlib import Path\n\n\n@dataclass(frozen=True)\nclass AnnealRecipe:\n    x_start_v: float = -1.0\n    x_stop_v: float = 1.0\n    x_points: int = 2\n    y_start_v: float = 1.0\n    y_stop_v: float = 3.0\n    y_points: int = 2\n    passes: int = 1\n    point_dwell_s: float = 0.001\n    mirror_settle_s: float = 0.0\n    serpentine: bool = False\n    anneal_rotation_coordinate: float = 35000.0\n    return_rotation_coordinate: float = 90000.0\n    return_rotation_stage: bool = True\n    maximum_open_time_s: float = 900.0\n    save_run_log: bool = True\n    output_root: str = ""\n\n\n@dataclass(frozen=True)\nclass InstrumentProfile:\n    profile_id: str = "REVIEW-REQUIRED"\n    approved: bool = False\n    sc10_port: str = "COM4"\n    sc10_baud_rate: int = 9600\n    sc10_timeout_s: float = 0.5\n    mirror_dio_pin: int = 2\n    minimum_mirror_voltage_v: float = -5.0\n    maximum_mirror_voltage_v: float = 5.0\n    home_x_voltage_v: float = 0.0\n    home_y_voltage_v: float = 0.0\n    rotation_stage_timeout_s: float = 60.0\n    rotation_min_coordinate: float = 35000.0\n    rotation_max_coordinate: float = 90000.0\n    maximum_open_time_s: float = 900.0\n    maximum_total_points: int = 1000000\n    require_return_stage: bool = True\n\n\ndef profile_path() -> Path:\n    override = os.environ.get("LABTOOLS_INSTRUMENT_PROFILE")\n    if override:\n        return Path(override).expanduser().resolve()\n    root = Path(os.environ.get("PROGRAMDATA", str(Path.home() / ".config")))\n    return root / "Labtools" / "instrument.json"\n\n\ndef _strict(cls, data):\n    if not isinstance(data, dict):\n        raise ValueError("Expected a JSON object")\n    defaults = asdict(cls())\n    unknown = set(data) - set(defaults)\n    if unknown:\n        raise ValueError("Unknown fields: " + ", ".join(sorted(unknown)))\n    for key, value in data.items():\n        expected = defaults[key]\n        if isinstance(expected, bool):\n            valid = type(value) is bool\n        elif isinstance(expected, int):\n            valid = type(value) is int\n        elif isinstance(expected, float):\n            valid = type(value) in (int, float) and math.isfinite(value)\n        else:\n            valid = isinstance(value, str)\n        if not valid:\n            raise ValueError(f"Invalid type or non-finite value for {key}")\n    return cls(**data)\n\n\ndef load_profile(path: Path | None = None) -> InstrumentProfile:\n    path = path or profile_path()\n    try:\n        data = json.loads(path.read_text(encoding="utf-8-sig"))\n    except FileNotFoundError as exc:\n        raise ValueError(f"Instrument profile missing: {path}. Ask the maintainer to install it.") from exc\n    if not isinstance(data, dict) or set(data) != {field.name for field in fields(InstrumentProfile)}:\n        raise ValueError("Instrument profile must explicitly specify every field; use the maintainer template")\n    return validate_profile(_strict(InstrumentProfile, data))\n\n\ndef validate_profile(profile):\n    _strict(InstrumentProfile, asdict(profile))\n    if not profile.approved or not profile.profile_id.strip() or profile.profile_id == "REVIEW-REQUIRED":\n        raise ValueError("The instrument profile must be reviewed and approved by the maintainer.")\n    if profile.minimum_mirror_voltage_v >= profile.maximum_mirror_voltage_v:\n        raise ValueError("Invalid mirror voltage limits")\n    if profile.rotation_min_coordinate > profile.rotation_max_coordinate:\n        raise ValueError("Invalid rotation-stage limits")\n    for key in ("sc10_timeout_s", "rotation_stage_timeout_s", "maximum_open_time_s", "maximum_total_points", "sc10_baud_rate"):\n        if getattr(profile, key) <= 0:\n            raise ValueError(f"Profile {key} must be positive")\n    if profile.mirror_dio_pin < 0 or not profile.sc10_port.strip():\n        raise ValueError("Invalid instrument connection settings")\n    for value in (profile.home_x_voltage_v, profile.home_y_voltage_v):\n        if not profile.minimum_mirror_voltage_v <= value <= profile.maximum_mirror_voltage_v:\n            raise ValueError("Home coordinate exceeds mirror limits")\n    return profile\n\n\ndef validate_recipe(recipe: AnnealRecipe, profile: InstrumentProfile) -> None:\n    _strict(AnnealRecipe, asdict(recipe))\n    validate_profile(profile)\n    if min(recipe.x_points, recipe.y_points, recipe.passes) < 1:\n        raise ValueError("Point counts and passes must be positive integers")\n    if min(recipe.point_dwell_s, recipe.mirror_settle_s) < 0:\n        raise ValueError("Dwell and settle cannot be negative")\n    total = recipe.x_points * recipe.y_points * recipe.passes\n    if total > profile.maximum_total_points:\n        raise ValueError("Recipe exceeds instrument point-count limit")\n    for key in ("x_start_v", "x_stop_v", "y_start_v", "y_stop_v"):\n        if not profile.minimum_mirror_voltage_v <= getattr(recipe, key) <= profile.maximum_mirror_voltage_v:\n            raise ValueError(f"{key} exceeds instrument voltage limits")\n    for key in ("anneal_rotation_coordinate", "return_rotation_coordinate"):\n        validate_stage_coordinate(getattr(recipe, key), profile)\n    if profile.require_return_stage and not recipe.return_rotation_stage:\n        raise ValueError("This instrument requires returning the rotation stage")\n    if not 0 < recipe.maximum_open_time_s <= profile.maximum_open_time_s:\n        raise ValueError("Requested maximum open time exceeds the instrument limit")\n    estimate = total * (recipe.point_dwell_s + recipe.mirror_settle_s)\n    if estimate > recipe.maximum_open_time_s:\n        raise ValueError("Estimated dwell/settle time exceeds requested maximum")\n    if not recipe.output_root or not Path(recipe.output_root).is_absolute():\n        raise ValueError("output_root must be an absolute path")\n\n\ndef validate_stage_coordinate(coordinate, profile=None):\n    profile = profile or load_profile()\n    if type(coordinate) not in (int, float) or not math.isfinite(coordinate):\n        raise ValueError("Invalid rotation coordinate")\n    if not profile.rotation_min_coordinate <= coordinate <= profile.rotation_max_coordinate:\n        raise ValueError("Rotation coordinate exceeds instrument limits")\n\n\ndef load_recipe(path: Path) -> AnnealRecipe:\n    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))\n    if not isinstance(data, dict) or set(data) != {"schema_version", "anneal"}:\n        raise ValueError("Recipe requires only schema_version and anneal")\n    if type(data["schema_version"]) is not int or data["schema_version"] != 1:\n        raise ValueError("Unsupported recipe schema")\n    return _strict(AnnealRecipe, data["anneal"])\n\n\ndef save_recipe(path: Path, recipe: AnnealRecipe) -> None:\n    _strict(AnnealRecipe, asdict(recipe))\n    path = Path(path)\n    path.parent.mkdir(parents=True, exist_ok=True)\n    temporary = path.with_suffix(path.suffix + ".tmp")\n    temporary.write_text(json.dumps({"schema_version": 1, "anneal": asdict(recipe)}, indent=2) + "\\n", encoding="utf-8")\n    temporary.replace(path)\n\n\ndef recipe_from_config(config) -> AnnealRecipe:\n    data = {field.name: getattr(config, field.name) for field in fields(AnnealRecipe)}\n    data["output_root"] = str(data["output_root"])\n    return _strict(AnnealRecipe, data)\n\n\ndef _resolved_values(recipe, profile):\n    validate_recipe(recipe, profile)\n    data = asdict(recipe)\n    data["output_root"] = Path(recipe.output_root)\n    for key in ("sc10_port", "sc10_baud_rate", "sc10_timeout_s", "mirror_dio_pin", "minimum_mirror_voltage_v", "maximum_mirror_voltage_v", "home_x_voltage_v", "home_y_voltage_v", "rotation_stage_timeout_s"):\n        data[key] = getattr(profile, key)\n    data["instrument_profile_id"] = profile.profile_id\n    data["instrument_profile_sha256"] = hashlib.sha256(json.dumps(asdict(profile), sort_keys=True).encode()).hexdigest()\n    try:\n        data["software_version"] = version("lab-tools")\n    except PackageNotFoundError:\n        data["software_version"] = "uninstalled"\n    return data\n\n\ndef build_config(recipe, profile=None):\n    from labtools.acquisition.laser_anneal import LaserAnnealConfig\n    return LaserAnnealConfig(**_resolved_values(recipe, profile or load_profile()))\n\n\ndef resolve_gui_config(config):\n    return replace(config, **_resolved_values(recipe_from_config(config), load_profile()))\n\n\ndef validate_run_config(config):\n    profile = load_profile()\n    expected = _resolved_values(recipe_from_config(config), profile)\n    for key, value in expected.items():\n        if getattr(config, key) != value:\n            raise ValueError(f"Configuration {key} does not match the instrument profile; use build_config().")\n    config.validate()\n\n\ndef initialise_workspace(root: Path):\n    root = Path(root).expanduser().resolve()\n    (root / "recipes").mkdir(parents=True, exist_ok=True)\n    (root / "data").mkdir(exist_ok=True)\n    path = root / "recipes" / "anneal.json"\n    if path.exists():\n        raise FileExistsError(f"Will not overwrite {path}")\n    save_recipe(path, replace(AnnealRecipe(), output_root=str(root / "data")))\n    return path\n', 'src/labtools/operator_cli.py': '"""Operator commands; validate/init/doctor do not connect to hardware."""\nfrom __future__ import annotations\n\nimport argparse\nimport json\nfrom dataclasses import asdict\nfrom pathlib import Path\n\nfrom labtools.config.anneal_workspace import (\n    initialise_workspace, load_profile, load_recipe, profile_path, validate_recipe,\n)\n\n\ndef main():\n    parser = argparse.ArgumentParser(prog="labtools")\n    sub = parser.add_subparsers(dest="command", required=True)\n    init = sub.add_parser("init", help="Create an editable operator workspace")\n    init.add_argument("directory", type=Path)\n    for name in ("validate", "anneal"):\n        command = sub.add_parser(name)\n        command.add_argument("recipe", type=Path)\n        if name == "anneal":\n            command.add_argument("--confirm-optical-path", action="store_true")\n    sub.add_parser("doctor", help="Check configuration only; no device access")\n    args = parser.parse_args()\n    try:\n        if args.command == "init":\n            print(initialise_workspace(args.directory))\n            return\n        profile = load_profile()\n        if args.command == "doctor":\n            print(f"Profile: {profile_path()} ({profile.profile_id})")\n            print("Configuration valid. No hardware was opened or tested.")\n            return\n        recipe = load_recipe(args.recipe)\n        validate_recipe(recipe, profile)\n        if args.command == "validate":\n            print(json.dumps(asdict(recipe), indent=2))\n            print("Recipe valid. No hardware was opened.")\n            return\n        if not args.confirm_optical_path:\n            parser.error("Hardware execution requires --confirm-optical-path after physical checks")\n        from labtools.config.anneal_workspace import build_config\n        from labtools.acquisition.laser_anneal import run_laser_anneal\n        print(run_laser_anneal(build_config(recipe, profile), status_callback=print))\n    except (ValueError, OSError) as exc:\n        parser.exit(2, f"Error: {exc}\\n")\n\n\ndef anneal_gui():\n    from labtools.gui.laser_anneal_gui import main as launch\n    launch()\n\n\ndef intensity_gui():\n    from labtools.gui.intensity_map_gui import main as launch\n    launch()\n\n\nif __name__ == "__main__":\n    main()\n', 'examples/profiles/instrument.example.json': '{\n  "profile_id": "REVIEW-REQUIRED",\n  "approved": false,\n  "sc10_port": "COM4",\n  "sc10_baud_rate": 9600,\n  "sc10_timeout_s": 0.5,\n  "mirror_dio_pin": 2,\n  "minimum_mirror_voltage_v": -5.0,\n  "maximum_mirror_voltage_v": 5.0,\n  "home_x_voltage_v": 0.0,\n  "home_y_voltage_v": 0.0,\n  "rotation_stage_timeout_s": 60.0,\n  "rotation_min_coordinate": 35000.0,\n  "rotation_max_coordinate": 90000.0,\n  "maximum_open_time_s": 900.0,\n  "maximum_total_points": 1000000,\n  "require_return_stage": true\n}\n', 'examples/experiments/run_anneal_recipe.py': '"""Editable runner. Defaults to validation; --run operates hardware."""\nimport argparse\nfrom pathlib import Path\nfrom labtools.config.anneal_workspace import load_profile, load_recipe, validate_recipe\n\n\ndef main():\n    parser = argparse.ArgumentParser()\n    parser.add_argument("recipe", type=Path)\n    parser.add_argument("--run", action="store_true")\n    args = parser.parse_args()\n    profile = load_profile()\n    recipe = load_recipe(args.recipe)\n    validate_recipe(recipe, profile)\n    print("Recipe valid")\n    if args.run:\n        answer = input("Optical path checked and ready to expose sample? Type RUN: ")\n        if answer != "RUN":\n            raise SystemExit("Cancelled")\n        from labtools.config.anneal_workspace import build_config\n        from labtools.acquisition.laser_anneal import run_laser_anneal\n        run_laser_anneal(build_config(recipe, profile), status_callback=print)\n\n\nif __name__ == "__main__":\n    main()\n', 'docs/operator-workspace.md': '# Operator workspace (annealing first phase)\n\nThe installer adds recipes/profile validation and GUI load/save controls for laser annealing.\nIntensity mapping receives a launcher only; its recipe migration is not implemented here.\nCamera preferences and existing QSettings persistence are retained. Recipes exclude hardware\nconnections, maintainer limits, camera preferences and safety acknowledgements.\n\n## Maintainer setup\n\nReview examples/profiles/instrument.example.json. All example limits and coordinates are\nunverified starting values, NOT a power calibration. Set real instrument limits and a unique\nprofile_id, then set approved to true only after review. Install the profile at\nC:/ProgramData/Labtools/instrument.json and use Windows permissions to allow operators read\naccess but no modification. Do not use a user-writable profile for a protected deployment.\nLABTOOLS_INSTRUMENT_PROFILE overrides the path for development/testing; it is NOT a security\nboundary. An operator able to execute arbitrary Python can bypass these software guardrails.\nDo not treat the approved flag as independent evidence of calibration or safety.\n\nRun uv sync after installation to refresh entry points. The installer does not modify uv.lock;\nreview any lock changes produced by uv sync. Do not install development code editable in the\nprotected deployment. Build/install a tested wheel with a separately created environment and\nmachine-accessible Python. Keep vendor drivers/DLLs available to each account. Windows ACL\nsetup and production deployment are deliberately NOT performed by this installer.\n\n## Operator use\n\nlabtools init "C:/Users/OPERATOR/Documents/Labtools Experiments"\nlabtools doctor\nlabtools validate "C:/Users/OPERATOR/Documents/Labtools Experiments/recipes/anneal.json"\nlabtools-anneal\n\nUse Load recipe / Save recipe / Save recipe as / Restore recipe defaults in the GUI.\nProfile hardware fields override GUI hardware preferences. Requested maximum open time may\nbe reduced but cannot exceed the profile. Recipe load clears the optical-path acknowledgement.\nLoad/save/reset is refused during an anneal. Recipe loading does not connect or move hardware.\nManual stage moves are checked against profile coordinates before confirmation.\n\nThe CLI anneal command operates hardware only with --confirm-optical-path. Physical checks\nand interlocks remain essential. Editable runner examples default to validation only.\n\n## Metadata and limitations\n\nExisting metadata.json includes resolved dataclass settings plus instrument_profile_id,\ninstrument_profile_sha256 and software_version. The profile digest identifies the resolved\nprofile, not a digital signature. The existing maximum-open-time check is an estimate based on dwell and settle, not an\nindependent hard shutter deadline. Native driver calls can block. Hardware interlocks remain\nrequired. This update does not change acquisition timing or device shutdown.\n\nThis update preserves existing camera and serial shutdown code; it does not fix driver hangs.\nThe existing QSettings values are per-user convenience settings, not named recipes.\nOnly maintainers should change the installed core; operators edit their workspace.\n\n## Existing scripts\n\nDirect calls to run_laser_anneal(LaserAnnealConfig(...)) now require resolved profile metadata.\nMigrate them to build_config(recipe, profile); the GUI is patched to resolve the profile.\nExisting hardware integration tests may need corresponding fixtures. The profile check runs\nbefore the public anneal function opens devices. Internal helpers and direct device wrappers\nare not a security boundary. The installer does not modify those wrappers.\n\nBackups live in .labtools-migrations; do not commit that folder. Rollback checks hashes and\nrefuses to overwrite files changed after installation, including by a formatter.\n', 'tests/test_anneal_workspace.py': '"""Hardware-free recipe and profile tests."""\nimport json\nfrom dataclasses import asdict, replace\nimport pytest\nfrom labtools.config.anneal_workspace import (\n    AnnealRecipe, InstrumentProfile, initialise_workspace, load_profile,\n    load_recipe, save_recipe, validate_recipe,\n)\n\n\ndef approved():\n    return replace(InstrumentProfile(), approved=True, profile_id="test-only")\n\n\ndef recipe(tmp_path):\n    return replace(AnnealRecipe(), output_root=str(tmp_path.resolve()))\n\n\ndef test_round_trip(tmp_path):\n    original = recipe(tmp_path)\n    path = tmp_path / "recipe.json"\n    save_recipe(path, original)\n    assert load_recipe(path) == original\n    validate_recipe(original, approved())\n\n\n@pytest.mark.parametrize("change", [\n    {"x_points": True}, {"x_points": 0}, {"x_start_v": float("nan")},\n    {"x_stop_v": 6.0}, {"maximum_open_time_s": 901.0},\n    {"return_rotation_stage": False}, {"anneal_rotation_coordinate": 1.0},\n    {"output_root": "relative"}, {"point_dwell_s": -1.0},\n])\ndef test_invalid_recipe(tmp_path, change):\n    with pytest.raises(ValueError):\n        validate_recipe(replace(recipe(tmp_path), **change), approved())\n\n\ndef test_unknown_hardware_field(tmp_path):\n    path = tmp_path / "bad.json"\n    data = asdict(recipe(tmp_path))\n    data["minimum_mirror_voltage_v"] = -100.0\n    path.write_text(json.dumps({"schema_version": 1, "anneal": data}))\n    with pytest.raises(ValueError):\n        load_recipe(path)\n\n\ndef test_unapproved_profile(tmp_path):\n    path = tmp_path / "profile.json"\n    path.write_text(json.dumps(asdict(InstrumentProfile())))\n    with pytest.raises(ValueError):\n        load_profile(path)\n\n\ndef test_workspace_does_not_overwrite(tmp_path):\n    initialise_workspace(tmp_path)\n    with pytest.raises(FileExistsError):\n        initialise_workspace(tmp_path)\n', 'src/labtools/config/recipe_ui.py': '"""Recipe controls for the existing anneal GUI; no automatic hardware actions."""\nfrom dataclasses import replace\nfrom pathlib import Path\nfrom PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QPushButton\nfrom labtools.config.anneal_workspace import (\n    AnnealRecipe, load_profile, load_recipe, recipe_from_config, save_recipe,\n    validate_recipe,\n)\n\nNUMERIC = {\n    "x_start_v": "x_start", "x_stop_v": "x_stop", "x_points": "x_points",\n    "y_start_v": "y_start", "y_stop_v": "y_stop", "y_points": "y_points",\n    "passes": "passes", "point_dwell_s": "dwell", "mirror_settle_s": "settle",\n    "anneal_rotation_coordinate": "anneal_stage_coordinate",\n    "return_rotation_coordinate": "return_stage_coordinate",\n    "maximum_open_time_s": "max_open",\n}\nCHECKS = {"serpentine": "serpentine", "return_rotation_stage": "return_stage", "save_run_log": "save_log"}\n\n\ndef _apply(window, recipe):\n    validate_recipe(recipe, load_profile())\n    widgets = [getattr(window, name) for name in (*NUMERIC.values(), *CHECKS.values(), "output_root")]\n    for key, name in NUMERIC.items():\n        widget = getattr(window, name)\n        value = getattr(recipe, key)\n        if not widget.minimum() <= value <= widget.maximum():\n            raise ValueError(f"{key} is outside this GUI\'s supported range")\n    old_blocks = [widget.blockSignals(True) for widget in widgets]\n    try:\n        for key, name in NUMERIC.items():\n            getattr(window, name).setValue(getattr(recipe, key))\n        for key, name in CHECKS.items():\n            getattr(window, name).setChecked(getattr(recipe, key))\n        window.output_root.setText(recipe.output_root)\n    finally:\n        for widget, old in zip(widgets, old_blocks, strict=True):\n            widget.blockSignals(old)\n    window.confirm.setChecked(False)\n    window._update_estimate()\n\n\ndef setup_recipe_controls(window):\n    window._operator_recipe_path = None\n    row = QHBoxLayout()\n\n    def guarded(operation):\n        try:\n            if window._thread is not None:\n                raise ValueError("Stop the anneal before changing or saving a recipe")\n            operation()\n        except (ValueError, OSError) as exc:\n            QMessageBox.critical(window, "Recipe error", str(exc))\n\n    def load():\n        filename, _ = QFileDialog.getOpenFileName(window, "Load recipe", str(Path.home()), "JSON recipes (*.json)")\n        if filename:\n            _apply(window, load_recipe(Path(filename)))\n            window._operator_recipe_path = Path(filename)\n            window.status.setText(f"Loaded recipe: {filename}")\n\n    def save(as_new=False):\n        path = None if as_new else window._operator_recipe_path\n        if path is None:\n            filename, _ = QFileDialog.getSaveFileName(window, "Save recipe", str(Path.home() / "anneal.json"), "JSON recipes (*.json)")\n            if not filename:\n                return\n            path = Path(filename)\n            if path.suffix.lower() != ".json":\n                path = path.with_suffix(".json")\n        recipe = recipe_from_config(window._build_config())\n        save_recipe(path, recipe)\n        window._operator_recipe_path = path\n        window.status.setText(f"Saved recipe: {path}")\n\n    def reset():\n        profile = load_profile()\n        recipe = replace(AnnealRecipe(), output_root=str(Path.home() / "Labtools Experiments" / "data"), maximum_open_time_s=profile.maximum_open_time_s)\n        _apply(window, recipe)\n        window._operator_recipe_path = None\n\n    for label, operation in (("Load recipe", load), ("Save recipe", save), ("Save recipe as", lambda: save(True)), ("Restore recipe defaults", reset)):\n        button = QPushButton(label)\n        button.clicked.connect(lambda checked=False, op=operation: guarded(op))\n        row.addWidget(button)\n    window.centralWidget().layout().insertLayout(1, row)\n    window.sc10_port.setReadOnly(True)\n    window.sc10_port.setToolTip("Connection is set by the instrument profile")\n    try:\n        window.sc10_port.setText(load_profile().sc10_port)\n    except (ValueError, OSError) as exc:\n        window.status.setText(str(exc))\n'}
MARKER = "# labtools operator workspace v1"
STATE = Path(".labtools-migrations/operator-workspace-v1")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def one(nodes, name):
    found = [node for node in nodes if getattr(node, "name", None) == name]
    if len(found) != 1:
        raise ValueError(f"Expected one {name}, found {len(found)}; no files changed")
    return found[0]


def edits(source, changes):
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(changes, reverse=True):
        lines[start:end] = [replacement]
    return "".join(lines)


def after_doc(node):
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.end_lineno
    return first.lineno - 1


def add_import(source, statement):
    tree = ast.parse(source)
    futures = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "__future__"]
    at = futures[-1].end_lineno if futures else after_doc(tree)
    return edits(source, [(at, at, statement + "\n")])


def patch_gui(source):
    if MARKER in source:
        raise ValueError("GUI already migrated")
    tree = ast.parse(source)
    window = one(tree.body, "LaserAnnealWindow")
    init = one(window.body, "__init__")
    build = one(window.body, "_build_config")
    move = one(window.body, "_move_stage_to_anneal")
    returns = [n for n in ast.walk(build) if isinstance(n, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.Call):
        raise ValueError("Unsupported configuration builder; no files changed")
    ret = returns[0]
    expression = ast.get_source_segment(source, ret.value)
    changes = [(ret.lineno - 1, ret.end_lineno, "        config = " + expression + "\n        return resolve_gui_config(config)\n")]
    changes.append((init.end_lineno, init.end_lineno, "        setup_recipe_controls(self)\n"))
    coords = [n for n in ast.walk(move) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "coordinate" for t in n.targets)]
    if len(coords) != 1:
        raise ValueError("Unsupported manual stage method; no files changed")
    at = coords[0].end_lineno
    changes.append((at, at, '        try:\n            validate_stage_coordinate(coordinate)\n        except (ValueError, OSError) as exc:\n            QMessageBox.critical(self, "Instrument profile error", str(exc))\n            return\n'))
    source = edits(source, changes)
    return add_import(source, MARKER + "\nfrom labtools.config.anneal_workspace import resolve_gui_config, validate_stage_coordinate\nfrom labtools.config.recipe_ui import setup_recipe_controls")


def patch_acquisition(source):
    if MARKER in source:
        raise ValueError("Acquisition already migrated")
    tree = ast.parse(source)
    config = one(tree.body, "LaserAnnealConfig")
    run = one(tree.body, "run_laser_anneal")
    # No changes to hardware sequencing, cleanup or scan timing.
    changes = [(after_doc(config), after_doc(config), '    instrument_profile_id: str = ""\n    instrument_profile_sha256: str = ""\n    software_version: str = ""\n')]
    changes.append((after_doc(run), after_doc(run), "    validate_run_config(config)\n"))
    return add_import(edits(source, changes), MARKER + "\nfrom labtools.config.anneal_workspace import validate_run_config")


def patch_project(source):
    data = tomllib.loads(source)
    entries = {"labtools": "labtools.operator_cli:main", "labtools-anneal": "labtools.operator_cli:anneal_gui", "labtools-intensity-map": "labtools.operator_cli:intensity_gui"}
    existing = data.get("project", {}).get("scripts", {})
    for name in entries:
        if name in existing:
            raise ValueError(f"Entry point {name} already exists; no files changed")
    block = "\n".join(f'{name} = "{value}"' for name, value in entries.items()) + "\n"
    if "scripts" in data.get("project", {}):
        indices = [i for i, line in enumerate(source.splitlines()) if line.strip() == "[project.scripts]"]
        if len(indices) != 1:
            raise ValueError("Unsupported project.scripts table")
        source = edits(source, [(indices[0] + 1, indices[0] + 1, block)])
    else:
        source = source.rstrip() + "\n\n[project.scripts]\n" + block
    tomllib.loads(source)
    return source


def rollback():
    manifest = json.loads((STATE / "manifest.json").read_text())
    for name, info in manifest.items():
        path = Path(name)
        if not path.exists() or digest(path.read_bytes()) != info["installed_sha256"]:
            raise ValueError(f"{name} changed since installation; restore manually from {STATE}.")
    for name, info in manifest.items():
        path = Path(name)
        if info["existed"]:
            shutil.copy2(STATE / "original" / name, path)
        else:
            path.unlink()
    (STATE / "manifest.json").rename(STATE / "rolled-back.json")
    print("[OK] Original files restored; newly installed files removed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.rollback:
        rollback()
        return
    if STATE.exists():
        raise ValueError("Prior migration state exists. Do not apply twice; retain backups.")
    paths = {"gui": Path("src/labtools/gui/laser_anneal_gui.py"), "acq": Path("src/labtools/acquisition/laser_anneal.py"), "project": Path("pyproject.toml")}
    changes = dict(PAYLOAD)
    for name in changes:
        if Path(name).exists():
            raise ValueError(f"New file already exists: {name}; no files changed")
    changes[str(paths["gui"])] = patch_gui(paths["gui"].read_text(encoding="utf-8-sig"))
    changes[str(paths["acq"])] = patch_acquisition(paths["acq"].read_text(encoding="utf-8-sig"))
    changes[str(paths["project"])] = patch_project(paths["project"].read_text(encoding="utf-8-sig"))
    for name, text in changes.items():
        if name.endswith(".py"):
            compile(text, name, "exec")
    print("Prepared and compiled:")
    for name in changes:
        print("  " + name)
    if args.check:
        print("[OK] Preflight passed. No files changed; no hardware opened.")
        return
    originals = {name: Path(name).read_bytes() if Path(name).exists() else None for name in changes}
    STATE.mkdir(parents=True)
    manifest = {}
    try:
        for name, text in changes.items():
            path = Path(name)
            old = originals[name]
            if old is not None:
                backup = STATE / "original" / name
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            manifest[name] = {"existed": old is not None, "installed_sha256": digest(path.read_bytes())}
        (STATE / "manifest.json").write_text(json.dumps(manifest, indent=2))
    except Exception:
        for name, old in originals.items():
            path = Path(name)
            if old is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old)
        raise
    print(f"[OK] Installed. Backups: {STATE}")
    print("No hardware was opened. Read docs/operator-workspace.md before use.")


if __name__ == "__main__":
    main()
