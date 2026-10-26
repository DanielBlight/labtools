"""Install offline intensity-map simulation. Run --check first.

No devices are opened. Apply on feature/hardware-simulation.
Backups and guarded --rollback are provided. Python 3.12+.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

PAYLOAD = {'src/labtools/simulation/__init__.py': '"""Offline simulation backends; no hardware imports."""\n', 'src/labtools/simulation/map_backend.py': '"""Explicit map-device selection. Simulation never imports hardware wrappers.\n\nThe synthetic scene is a development model, not a physical calibration.\n"""\nfrom __future__ import annotations\n\nimport hashlib\nimport math\nimport time\nfrom contextlib import ExitStack, contextmanager\nfrom dataclasses import dataclass, field\n\nimport numpy as np\n\nMODEL_VERSION = \'gaussian-scene-v1\'\n\n\n@dataclass\nclass SimulatedMapState:\n    """One shared state for mirror, gate and counter in a single map session."""\n\n    x_v: float = 0.0\n    y_v: float = 0.0\n    gate_open: bool = False\n    measurements: int = 0\n    moves: list = field(default_factory=list)\n    closed: bool = False\n\n\nclass SimulatedMirror:\n    def __init__(self, state, config):\n        self.state = state\n        self.config = config\n\n    def move(self, x_voltage, y_voltage):\n        values = (float(x_voltage), float(y_voltage))\n        if self.state.closed:\n            raise RuntimeError(\'Simulated session is closed\')\n        if not all(math.isfinite(v) and self.config.safe_voltage_min_v <= v <= self.config.safe_voltage_max_v for v in values):\n            raise ValueError(\'Simulated mirror voltage outside configured limits\')\n        self.state.x_v, self.state.y_v = values\n        self.state.moves.append(values)\n\n    def home(self):\n        self.move(0.0, 0.0)\n\n\nclass SimulatedGate:\n    def __init__(self, state):\n        self.state = state\n\n    def open(self):\n        if self.state.closed:\n            raise RuntimeError(\'Simulated session is closed\')\n        self.state.gate_open = True\n\n    def close(self):\n        self.state.gate_open = False\n\n\nclass SimulatedTimeController:\n    def __init__(self, state, config):\n        self.state = state\n        self.config = config\n        self.channel_settings = {}\n\n    def configure_channel(self, channel, *, threshold_v, edge, enabled=True):\n        if channel not in (1, 2, 3, 4) or edge not in (\'rising\', \'falling\'):\n            raise ValueError(\'Invalid simulated channel configuration\')\n        if not math.isfinite(threshold_v):\n            raise ValueError(\'Threshold must be finite\')\n        self.channel_settings[channel] = (threshold_v, edge, enabled)\n\n    def get_simultaneous_counts(self, channels, integration_time_s):\n        integration_time_s = float(integration_time_s)\n        if self.state.closed:\n            raise RuntimeError(\'Simulated session is closed\')\n        if not math.isfinite(integration_time_s) or integration_time_s <= 0:\n            raise ValueError(\'Integration time must be finite and positive\')\n        if any(ch not in self.channel_settings or not self.channel_settings[ch][2] for ch in channels):\n            raise ValueError(\'Configure and enable selected channels first\')\n        limit = self.config.simulation_fail_after_points\n        if limit is not None and self.state.measurements >= limit:\n            raise TimeoutError(\'Injected SIMULATION counter timeout\')\n        if self.config.simulation_realtime:\n            time.sleep(integration_time_s)\n        c = self.config\n        sx = max(abs(c.x_stop_v - c.x_start_v), 1e-6)\n        sy = max(abs(c.y_stop_v - c.y_start_v), 1e-6)\n        u = (self.state.x_v - (c.x_start_v + c.x_stop_v) / 2) / sx\n        v = (self.state.y_v - (c.y_start_v + c.y_stop_v) / 2) / sy\n        scene = 2000.0 + 80000.0 * math.exp(-0.5 * ((u / .17) ** 2 + (v / .20) ** 2))\n        scene += 18000.0 * math.exp(-0.5 * (((u - .27) / .09) ** 2 + ((v + .22) / .12) ** 2))\n        result = {}\n        for channel in channels:\n            # Per-position/channel RNG makes resumed maps match uninterrupted maps.\n            key = f\'{MODEL_VERSION}|{c.simulation_seed}|{self.state.x_v.hex()}|{self.state.y_v.hex()}|{channel}|{integration_time_s.hex()}\'\n            seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:16], \'little\')\n            rng = np.random.default_rng(seed)\n            rate = scene * (1.0 + .25 * (channel - 1)) if self.state.gate_open else 0.0\n            result[channel] = int(rng.poisson(rate * integration_time_s))\n        self.state.measurements += 1\n        return result\n\n\n@contextmanager\ndef open_map_devices(config):\n    """Yield mirror, gate, controller; never silently fall back to simulation."""\n    if config.backend == \'simulation\':\n        state = SimulatedMapState()\n        mirror = SimulatedMirror(state, config)\n        gate = SimulatedGate(state)\n        controller = SimulatedTimeController(state, config)\n        try:\n            yield mirror, gate, controller\n        finally:\n            gate.close()\n            state.closed = True\n        return\n    if config.backend != \'real\':\n        raise ValueError(\'backend must be real or simulation\')\n    # Import native libraries only after explicit real selection.\n    from labtools.devices.idq_time_controller import IDQTimeController\n    from labtools.devices.labjack_u6 import LabJackU6\n    from labtools.devices.scanning_mirror import ScanningMirror\n    from labtools.devices.spad_gate import SPADGate\n\n    with ExitStack() as stack:\n        labjack = stack.enter_context(LabJackU6())\n        controller = stack.enter_context(IDQTimeController(config.time_controller_address))\n        mirror = ScanningMirror(labjack, dio_pin=config.mirror_dio_pin)\n        gate = SPADGate(labjack, pin=config.spad_gate_pin)\n        yield mirror, gate, controller\n\n\nclass LazyITC4000:\n    """Compatibility factory; no VISA import until a real connection is requested."""\n\n    DEFAULT_ADDRESS = \'__INSTALLER_LASER_ADDRESS__\'\n\n    def __new__(cls, *args, **kwargs):\n        from labtools.devices.itc4000 import ITC4000\n        return ITC4000(*args, **kwargs)\n', 'src/labtools/simulation/intensity_map.py': '"""Run synthetic maps only: python -m labtools.simulation.intensity_map."""\nfrom __future__ import annotations\n\nimport argparse\nfrom dataclasses import replace\nfrom pathlib import Path\n\n\ndef main():\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument(\'--gui\', action=\'store_true\')\n    parser.add_argument(\'--output\', type=Path, default=Path.home() / \'Labtools Simulation\')\n    parser.add_argument(\'--points\', type=int, default=15)\n    parser.add_argument(\'--seed\', type=int, default=0)\n    parser.add_argument(\'--realtime\', action=\'store_true\')\n    parser.add_argument(\'--stop-after\', type=int)\n    parser.add_argument(\'--resume\', type=Path)\n    args = parser.parse_args()\n    if args.points < 2 or args.seed < 0 or (args.stop_after is not None and args.stop_after < 1):\n        parser.error(\'points >= 2, seed >= 0 and stop-after >= 1 are required\')\n    if args.gui:\n        import sys\n        from PyQt6.QtWidgets import QApplication\n        from PyQt6.QtGui import QFont\n        from labtools.gui.intensity_map_gui import IntensityMapWindow\n        app = QApplication([sys.argv[0]])\n        app.setFont(QFont(\'Segoe UI\', 9))\n        window = IntensityMapWindow()\n        window.simulation_mode.setChecked(True)\n        window.output_root.setText(str(args.output))\n        window.x_points.setValue(args.points)\n        window.y_points.setValue(args.points)\n        window.show()\n        raise SystemExit(app.exec())\n    from labtools.acquisition.intensity_map import (\n        IntensityMapConfig, acquire_intensity_map, config_from_resume_directory,\n    )\n    if args.resume:\n        config = config_from_resume_directory(args.resume)\n        if config.backend != \'simulation\':\n            parser.error(\'This runner refuses to resume real-hardware data\')\n        config = replace(config, simulation_realtime=args.realtime, simulation_fail_after_points=None)\n    else:\n        config = IntensityMapConfig(\n            x_start_v=-1., x_stop_v=1., x_points=args.points,\n            y_start_v=-1., y_stop_v=1., y_points=args.points,\n            integration_time_s=.02, settle_time_s=0.,\n            channels=(1, 2), channel_thresholds_v=(.1, .1),\n            channel_edges=(\'rising\', \'rising\'), output_root=args.output,\n            backend=\'simulation\', simulation_seed=args.seed,\n            simulation_realtime=args.realtime,\n        )\n    latest = [0]\n    def progress(snapshot):\n        latest[0] = snapshot.points_complete\n        print(f\'SYNTHETIC: {snapshot.points_complete}/{snapshot.total_points}\')\n    result = acquire_intensity_map(\n        config, resume_directory=args.resume, progress_callback=progress,\n        cancel_requested=lambda: args.stop_after is not None and latest[0] >= args.stop_after,\n    )\n    print(\'SYNTHETIC DATA ONLY:\', result.output_directory)\n    print(\'Complete:\', result.complete)\n\n\nif __name__ == \'__main__\':\n    main()\n', 'tests/test_intensity_map_simulation.py': '"""Offline tests of the real acquisition loop with simulated devices."""\nfrom __future__ import annotations\n\nimport builtins\nimport json\nimport os\nimport subprocess\nimport sys\nfrom dataclasses import replace\nfrom pathlib import Path\n\nimport numpy as np\nimport pytest\n\nfrom labtools.acquisition.intensity_map import (\n    CHECKPOINT_FILENAME, METADATA_FILENAME, IntensityMapConfig,\n    acquire_intensity_map, config_from_resume_directory,\n)\nfrom labtools.simulation.map_backend import open_map_devices\n\n\n@pytest.fixture\ndef config(tmp_path):\n    return IntensityMapConfig(\n        x_start_v=-1., x_stop_v=1., x_points=5,\n        y_start_v=-1., y_stop_v=1., y_points=5,\n        channels=(1, 2), channel_thresholds_v=(.1, .1),\n        channel_edges=(\'rising\', \'falling\'), integration_time_s=.02,\n        settle_time_s=0., output_root=tmp_path,\n        backend=\'simulation\', simulation_seed=42,\n        simulation_realtime=False, save_results=False,\n        checkpoint_every_points=2,\n    )\n\n\n@pytest.fixture(autouse=True)\ndef no_native_imports(monkeypatch):\n    original = builtins.__import__\n    blocked = (\'u6\', \'LabJackPython\', \'pyvisa\', \'zmq\', \'pyft232\', \'pylablib\', \'labtools.devices\')\n    def guarded(name, *args, **kwargs):\n        if any(name == prefix or name.startswith(prefix + \'.\') for prefix in blocked):\n            raise AssertionError(\'Hardware import forbidden in simulation: \' + name)\n        return original(name, *args, **kwargs)\n    monkeypatch.setattr(builtins, \'__import__\', guarded)\n\n\ndef test_complete_two_channel_map(config):\n    result = acquire_intensity_map(config)\n    assert result.complete\n    assert result.counts.shape == (2, 5, 5)\n    assert result.completed_mask.all()\n    assert np.all(result.counts >= 0)\n    np.testing.assert_allclose(result.summed_count_rate_cps, result.count_rates_cps.sum(axis=0))\n    assert result.output_directory.parent.name == \'SIMULATION\'\n    assert (result.output_directory / \'SYNTHETIC_DATA.txt\').exists()\n    metadata = json.loads((result.output_directory / METADATA_FILENAME).read_text())\n    assert metadata[\'synthetic_data\'] is True\n    assert metadata[\'backend\'] == \'simulation\'\n\n\ndef test_position_changes_counts_and_gate(config):\n    with open_map_devices(config) as (mirror, gate, counter):\n        counter.configure_channel(1, threshold_v=.1, edge=\'rising\')\n        mirror.move(0., 0.)\n        assert counter.get_simultaneous_counts((1,), .1)[1] == 0\n        gate.open()\n        centre = counter.get_simultaneous_counts((1,), .1)[1]\n        mirror.move(-1., -1.)\n        corner = counter.get_simultaneous_counts((1,), .1)[1]\n        assert centre > corner\n        state = mirror.state\n    assert state.closed and not state.gate_open\n\n\ndef test_stop_and_resume_matches_uninterrupted(config):\n    latest = [0]\n    def progress(snapshot):\n        latest[0] = snapshot.points_complete\n    partial = acquire_intensity_map(config, progress_callback=progress,\n                                    cancel_requested=lambda: latest[0] >= 7)\n    assert not partial.complete\n    assert partial.completed_mask.sum() == 7\n    assert (partial.output_directory / CHECKPOINT_FILENAME).exists()\n    restored = config_from_resume_directory(partial.output_directory)\n    assert restored.backend == \'simulation\'\n    resumed = acquire_intensity_map(restored, resume_directory=partial.output_directory)\n    assert resumed.complete and resumed.resumed\n    np.testing.assert_array_equal(resumed.counts[:, partial.completed_mask], partial.counts[:, partial.completed_mask])\n    np.testing.assert_array_equal(resumed.session_ids[partial.completed_mask], partial.session_ids[partial.completed_mask])\n    fresh = acquire_intensity_map(replace(config, output_root=config.output_root / \'fresh\'))\n    np.testing.assert_array_equal(resumed.counts, fresh.counts)\n\n\ndef test_failure_retains_checkpoint_and_resume(config):\n    failed = replace(config, simulation_fail_after_points=4)\n    with pytest.raises(TimeoutError, match=\'SIMULATION\'):\n        acquire_intensity_map(failed)\n    directory = next((config.output_root / \'SIMULATION\').iterdir())\n    with np.load(directory / CHECKPOINT_FILENAME) as checkpoint:\n        assert checkpoint[\'completed_mask\'].sum() == 4\n    restored = replace(config_from_resume_directory(directory), simulation_fail_after_points=None)\n    assert acquire_intensity_map(restored, resume_directory=directory).complete\n\n\ndef test_cross_backend_resume_rejected_before_hardware(config):\n    partial = acquire_intensity_map(config, cancel_requested=lambda: True)\n    with pytest.raises(ValueError, match=\'backend\'):\n        acquire_intensity_map(replace(config, backend=\'real\'), resume_directory=partial.output_directory)\n\n\ndef test_changed_seed_resume_rejected(config):\n    partial = acquire_intensity_map(config, cancel_requested=lambda: True)\n    with pytest.raises(ValueError, match=\'simulation_seed\'):\n        acquire_intensity_map(replace(config, simulation_seed=999), resume_directory=partial.output_directory)\n\n\n@pytest.mark.parametrize(\'backend\', [\'invalid\', \'\', \'SIMULATION\'])\ndef test_invalid_backend(config, backend):\n    with pytest.raises(ValueError, match=\'backend\'):\n        replace(config, backend=backend).validate()\n\n\n@pytest.mark.parametrize(\'seed\', [-1, 1.5, True])\ndef test_invalid_seed(config, seed):\n    with pytest.raises(ValueError, match=\'seed\'):\n        replace(config, simulation_seed=seed).validate()\n\n\ndef test_no_fallback_on_real_failure(config):\n    with pytest.raises(AssertionError, match=\'Hardware import forbidden\'):\n        with open_map_devices(replace(config, backend=\'real\')):\n            pytest.fail(\'Real backend unexpectedly connected\')\n\n\ndef test_single_channel(config):\n    single = replace(config, channels=(3,), channel_thresholds_v=(.1,), channel_edges=(\'rising\',))\n    result = acquire_intensity_map(single)\n    assert result.counts.shape == (1, 5, 5)\n    np.testing.assert_allclose(result.summed_count_rate_cps, result.count_rates_cps[0])\n\n\ndef test_final_outputs_labelled(config):\n    result = acquire_intensity_map(replace(config, save_results=True))\n    with np.load(result.output_directory / \'intensity_map_complete.npz\') as data:\n        assert data[\'synthetic_data\'].item() is True\n        assert data[\'backend\'].item() == \'simulation\'\n    assert (result.output_directory / \'summed_intensity_map.png\').exists()\n\n\ndef test_import_isolation_in_fresh_interpreter(tmp_path):\n    # Block native imports before importing any labtools acquisition code.\n    code = \'\'\'\nimport importlib.abc\nimport sys\nfrom pathlib import Path\nclass Block(importlib.abc.MetaPathFinder):\n    def find_spec(self, fullname, path=None, target=None):\n        if fullname.startswith((\'labtools.devices\', \'u6\', \'LabJackPython\', \'pyvisa\', \'zmq\', \'pylablib\', \'pyft232\')):\n            raise AssertionError(\'Native import attempted: \' + fullname)\nsys.meta_path.insert(0, Block())\nfrom labtools.acquisition.intensity_map import IntensityMapConfig, acquire_intensity_map\nc = IntensityMapConfig(x_start_v=-1., x_stop_v=1., x_points=2,\n    y_start_v=-1., y_stop_v=1., y_points=2, backend=\'simulation\',\n    simulation_realtime=False, settle_time_s=0., save_results=False,\n    output_root=Path(sys.argv[1]))\nassert acquire_intensity_map(c).complete\n\'\'\'\n    env = os.environ.copy()\n    env[\'MPLBACKEND\'] = \'Agg\'\n    env[\'PYTHONPATH\'] = str(Path(__file__).resolve().parents[1] / \'src\')\n    completed = subprocess.run([sys.executable, \'-c\', code, str(tmp_path)], env=env,\n                               capture_output=True, text=True, timeout=30)\n    assert completed.returncode == 0, completed.stdout + completed.stderr\n\n\ndef gui_method(name):\n    import ast\n    import copy\n    source = Path(__file__).resolve().parents[1] / \'src/labtools/gui/intensity_map_gui.py\'\n    cls = next(n for n in ast.parse(source.read_text(encoding=\'utf-8-sig\')).body\n               if isinstance(n, ast.ClassDef) and n.name == \'IntensityMapWindow\')\n    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name))\n    method.decorator_list = []\n    future = ast.ImportFrom(module=\'__future__\', names=[ast.alias(name=\'annotations\')], level=0)\n    ns = {\'Path\': Path}\n    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, method], type_ignores=[])), str(source), \'exec\'), ns)\n    return ns[name]\n\n\n@pytest.mark.parametrize(\'name\', [\'connect_laser\', \'turn_laser_on\', \'turn_laser_off\', \'set_laser_current\'])\ndef test_simulation_laser_actions_are_guarded(name):\n    from types import SimpleNamespace\n    messages = []\n    window = SimpleNamespace(simulation_mode=SimpleNamespace(isChecked=lambda: True), set_status=messages.append)\n    gui_method(name)(window)\n    assert \'disabled\' in messages[-1]\n\n\ndef test_legacy_real_signature_unchanged(config):\n    signature = replace(config, backend=\'real\').checkpoint_signature()\n    assert \'backend\' not in signature\n    assert \'simulation_seed\' not in signature\n', 'docs/intensity-map-simulation.md': '# Offline intensity-map simulation, v1\n\nInstall on `feature/hardware-simulation`, from a clean committed checkout.\nThe self-contained installer updates the acquisition and GUI modules in place\nusing AST-located edits. It adds a simulation package, tests and this guide.\nIt does not replace the entire GUI or device wrappers.\n\n## Install\n\n    uv run python install_intensity_map_simulation.py --check\n    uv run python install_intensity_map_simulation.py\n    uv run python -m pytest --noconftest tests/test_intensity_map_simulation.py -q\n\n`--noconftest` isolates this test file from existing hardware fixtures and\ncollection-time native imports in the repository\'s conftest files. The tests\nprovide their own fixtures. Do not add `--run-hardware` to this command.\n\nNo additional dependencies are required beyond the project\'s existing NumPy,\nMatplotlib, pytest and (for the GUI) PyQt6. The installer itself uses only the\nstandard library. It does not run pip, uv sync, or connect devices.\n\n## Launch\n\n    uv run python -m labtools.simulation.intensity_map --gui\n\nThis starts the existing intensity-map GUI with simulation selected. It shows\na SIMULATION banner and disables real laser actions. The normal GUI launcher\nstill defaults to real mode; select the explicit Simulation checkbox to use\nsynthetic devices. Backend selection is not persisted and cannot change while\na map or laser session is active. Close/reopen the GUI to release a connected\nreal laser before switching to simulation.\n\nA headless two-channel synthetic map:\n\n    uv run python -m labtools.simulation.intensity_map --points 15\n\nA stopped map:\n\n    uv run python -m labtools.simulation.intensity_map --points 15 --stop-after 40\n\nResume using the printed dataset directory:\n\n    uv run python -m labtools.simulation.intensity_map --resume "FULL DATASET PATH"\n\nThe headless runner defaults to fast operation; `--realtime` honours integration\nand settling delays. The GUI uses real-time delays so Stop can be exercised.\nThe headless --seed option applies to new headless maps; the GUI currently uses\nseed 0 and has no seed editor. A resumed map restores its saved seed.\n\n## Model and provenance\n\nThe mirror, SPAD gate and counter share a per-session state. Counts come from\na synthetic two-Gaussian scene plus background and Poisson counting noise.\nThe scene is scaled to the requested voltage range, not to physical distances.\nThreshold and edge settings are recorded/validated but do not model detector\nelectronics. Integration time scales expected counts. Closed gate gives zero.\nThe per-coordinate/channel seed makes resumed counts match uninterrupted maps.\nThis is synthetic development data, not a model validated against your optics.\n\nNew synthetic datasets go under an additional SIMULATION subdirectory and have\nSYNTHETIC_DATA.txt plus explicit JSON and final NPZ provenance. PNG titles and\nlive plot titles are marked SYNTHETIC. Existing CSV names/schema are retained:\nkeep them with the dataset metadata and marker, not as standalone measurements.\nReal checkpoint signatures retain their legacy shape. Cross-backend resume is\nrejected before device creation. A simulation never silently replaces a failed\nreal connection. Simulation seed/model changes invalidate simulation resume;\nreal-time delay and fault-injection changes do not.\n\nFailure injection is available programmatically:\n\n    config = dataclasses.replace(config, simulation_fail_after_points=4)\n\nClear this option before resuming. It counts measurements in the current session.\n\n## Limits and validation\n\nThis first phase covers intensity mapping only. It does not simulate the camera,\nannealing, shutter, rotation stage, spectrometer or laser power. Real laser\ncontrols are disabled rather than simulated. Existing native-driver issues and\nphysical safety checks are not solved by simulation.\n\nThe package includes offline tests for one/two-channel maps, stop/resume,\nfault checkpoints, seed reproducibility, provenance, backend isolation and GUI\nlaser-action guards. These do not prove Qt rendering, real-device behaviour,\nphysical timing, wiring or calibration. Run the tests on your actual checkout.\n\nThe development validation used a representative acquisition fixture rebuilt\nfrom the retrieved source interfaces, not a byte-for-byte local copy of the\ncurrent repository. Full Qt/hardware execution was unavailable.\n\n## Rollback\n\n    uv run python install_intensity_map_simulation.py --rollback\n\nBackups are in .labtools-migrations/intensity-map-simulation-v1. Do not commit\nthat directory. Rollback refuses to overwrite files modified after installation,\nincluding formatting changes. Review the diff and keep the backup until tested.\n'}

"""AST-located source edits, refusing unknown layouts rather than guessing."""
import ast


def one(nodes, name):
    matches = [n for n in nodes if getattr(n, 'name', None) == name]
    if len(matches) != 1:
        raise ValueError(f'Expected one {name}; found {len(matches)}. No changes written.')
    return matches[0]


def apply(source, edits):
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    result = ''.join(lines)
    compile(result, '<proposed update>', 'exec')
    return result


def body_start(node):
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.end_lineno
    return first.lineno - 1


def patch_acquisition(source):
    tree = ast.parse(source)
    cls = one(tree.body, 'IntensityMapConfig')
    if any(isinstance(n, ast.AnnAssign) and getattr(n.target, 'id', '') == 'backend' for n in cls.body):
        raise ValueError('A backend already exists; refusing duplicate migration')
    acquire = one(tree.body, 'acquire_intensity_map')
    edits = []
    modules = {'labtools.devices.idq_time_controller', 'labtools.devices.labjack_u6',
               'labtools.devices.scanning_mirror', 'labtools.devices.spad_gate'}
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module in modules]
    if len(imports) != 4:
        raise ValueError('Expected four device imports in acquisition module')
    for n in imports:
        edits.append((n.lineno - 1, n.end_lineno, ''))
    first = min(n.lineno for n in imports) - 1
    edits.append((first, first, 'from labtools.simulation.map_backend import MODEL_VERSION, open_map_devices\n'))
    fields = [n for n in cls.body if isinstance(n, ast.AnnAssign)]
    edits.append((fields[-1].end_lineno, fields[-1].end_lineno, '''    backend: str = "real"
    simulation_seed: int = 0
    simulation_realtime: bool = True
    simulation_fail_after_points: int | None = None
'''))
    validate = one(cls.body, 'validate')
    edits.append((body_start(validate), body_start(validate), '''        if self.backend not in {"real", "simulation"}:
            raise ValueError("backend must be real or simulation")
        if type(self.simulation_seed) is not int or self.simulation_seed < 0:
            raise ValueError("simulation_seed must be a nonnegative integer")
        if type(self.simulation_realtime) is not bool:
            raise ValueError("simulation_realtime must be bool")
        if self.simulation_fail_after_points is not None and (
            type(self.simulation_fail_after_points) is not int or self.simulation_fail_after_points < 0
        ):
            raise ValueError("simulation_fail_after_points must be nonnegative or None")
        if not all(np.isfinite(v) for v in (
            self.integration_time_s, self.settle_time_s,
            self.safe_voltage_min_v, self.safe_voltage_max_v,
        )):
            raise ValueError("Timing and voltage limits must be finite")
'''))
    signature = one(cls.body, 'checkpoint_signature')
    ret = [n for n in signature.body if isinstance(n, ast.Return)]
    if len(ret) != 1 or not isinstance(ret[0].value, ast.Dict):
        raise ValueError('Unexpected checkpoint signature implementation')
    node = ret[0]
    text = ast.unparse(node.value)
    replacement = '        signature = ' + text + '\n'
    replacement += '''        if self.backend == "simulation":
            signature.update(backend="simulation", simulation_seed=self.simulation_seed,
                             simulation_model=MODEL_VERSION)
        return signature
'''
    edits.append((node.lineno - 1, node.end_lineno, replacement))
    # Preserve legacy real checkpoint signatures; explicitly forbid cross-backend resume.
    resume = one(tree.body, '_validate_resume_config')
    edits.append((body_start(resume), body_start(resume), '''    if metadata.get("backend", "real") != config.backend:
        raise ValueError("Cannot resume data with a different real/simulation backend")
'''))
    metadata = one(tree.body, '_write_metadata')
    payload = [n for n in metadata.body if isinstance(n, ast.Assign) and any(ast.unparse(t) == 'payload' for t in n.targets)]
    if len(payload) != 1:
        raise ValueError('Cannot identify metadata payload')
    at = payload[0].end_lineno
    edits.append((at, at, '''    payload.update(synthetic_data=config.backend == "simulation",
                   simulation_model=MODEL_VERSION if config.backend == "simulation" else None)
'''))
    # Replace only the hardware setup header; preserve the existing scan body.
    contexts = [n for n in ast.walk(acquire) if isinstance(n, ast.With) and
                any('LabJackU6' in ast.unparse(item.context_expr) for item in n.items)]
    if len(contexts) != 1:
        raise ValueError('Cannot identify hardware setup context')
    context = contexts[0]
    if len(context.body) < 3 or not isinstance(context.body[0], ast.Assign) or not isinstance(context.body[1], ast.Assign):
        raise ValueError('Unexpected mirror/gate setup layout')
    if ast.unparse(context.body[0].targets[0]) != 'mirror' or ast.unparse(context.body[1].targets[0]) != 'gate':
        raise ValueError('Expected mirror and gate setup before channel configuration')
    indent = ' ' * context.col_offset
    edits.append((context.lineno - 1, context.body[1].end_lineno,
                  indent + 'with open_map_devices(config) as (mirror, gate, controller):\n'))
    # Separate output roots and add a plain-language marker before any data are saved.
    assignments = [n for n in ast.walk(acquire) if isinstance(n, ast.Assign) and
                   isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == '_new_output_directory']
    if len(assignments) != 1:
        raise ValueError('Cannot identify output directory creation')
    n = assignments[0]
    edits.append((n.lineno - 1, n.end_lineno, '''        root = Path(config.output_root)
        if config.backend == "simulation":
            root = root / "SIMULATION"
        if config.backend == "simulation":
            output_directory = root / datetime.now(UTC).strftime("synthetic_%Y%m%d-%H%M%S-%f")
            output_directory.mkdir(parents=True, exist_ok=False)
        else:
            output_directory = _new_output_directory(root)
        if config.backend == "simulation":
            (output_directory / "SYNTHETIC_DATA.txt").write_text(
                "SIMULATION: synthetic development data, not experimental measurements.\\n",
                encoding="utf-8",
            )
'''))
    settle = [n for n in ast.walk(acquire) if isinstance(n, ast.If) and ast.unparse(n.test) == 'config.settle_time_s']
    if len(settle) != 1:
        raise ValueError('Cannot identify settling condition')
    n = settle[0]
    edits.append((n.lineno - 1, n.lineno, ' ' * n.col_offset +
                  'if config.settle_time_s and (config.backend == "real" or config.simulation_realtime):\n'))
    final = one(tree.body, '_save_final_outputs')
    # Add provenance directly inside the final NPZ, and label the PNG.
    calls = [n for n in ast.walk(final) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'np.savez_compressed']
    if len(calls) != 1:
        raise ValueError('Cannot identify final NPZ write')
    n = calls[0]
    edits.append((n.end_lineno - 1, n.end_lineno - 1, '''        backend=config.backend,
        synthetic_data=config.backend == "simulation",
'''))
    title = [n for n in ast.walk(final) if isinstance(n, ast.Call) and ast.unparse(n.func) == 'plot_intensity_map']
    if len(title) != 1:
        raise ValueError('Cannot identify final plot')
    call = title[0]
    title_kw = next(k for k in call.keywords if k.arg == 'title')
    if title_kw.value.lineno != title_kw.value.end_lineno:
        raise ValueError('Unexpected plot title layout')
    edits.append((title_kw.value.lineno - 1, title_kw.value.end_lineno,
                  '        title=("SYNTHETIC — " if config.backend == "simulation" else "") + _plot_title(result.channels),\n'))
    return apply(source, edits)


GUI_METHODS = '''
    def _simulation_changed(self, enabled):
        """Choose backend explicitly, never while a session owns hardware."""
        if self._thread is not None or self.laser is not None:
            previous = self.simulation_mode.blockSignals(True)
            self.simulation_mode.setChecked(not enabled)
            self.simulation_mode.blockSignals(previous)
            QMessageBox.warning(self, "Backend locked", "Stop the map and disconnect the laser before switching backend.")
            return
        if enabled:
            self._real_output_root = self.output_root.text()
            self.output_root.setText(str(Path.home() / "Labtools Simulation"))
        elif hasattr(self, "_real_output_root"):
            self.output_root.setText(self._real_output_root)
        self.simulation_banner.setVisible(enabled)
        self.setWindowTitle("SIMULATION — Intensity Map" if enabled else "Intensity Map Acquisition")
        self.laser_group.setEnabled(not enabled)
        self.set_laser_indicator(False)
        self.set_status("SIMULATION — synthetic data only" if enabled else "Real hardware selected")

'''


def patch_gui(source):
    tree = ast.parse(source)
    cls = one(tree.body, 'IntensityMapWindow')
    if 'simulation_mode' in source:
        raise ValueError('Simulation GUI controls already exist')
    edits = []
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == 'labtools.devices.itc4000']
    if len(imports) != 1:
        raise ValueError('Expected ITC4000 import')
    n = imports[0]
    edits.append((n.lineno - 1, n.end_lineno,
                  'from labtools.simulation.map_backend import LazyITC4000 as ITC4000\n'))
    init = one(cls.body, '__init__')
    calls = [n for n in init.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and ast.unparse(n.value.func) == 'self._build_map_controls']
    if len(calls) != 1:
        raise ValueError('Cannot identify map controls construction')
    n = calls[0]
    edits.append((n.end_lineno, n.end_lineno, '''        self.simulation_mode = QCheckBox("Simulation — no hardware")
        self.simulation_mode.setChecked(False)
        controls_layout.insertWidget(0, self.simulation_mode)
'''))
    edits.append((init.end_lineno, init.end_lineno, '''        self.simulation_banner = QLabel("SIMULATION — SYNTHETIC DATA ONLY")
        self.simulation_banner.setStyleSheet("background:#fff3cd;color:#664d03;padding:6px;font-weight:bold;")
        self.statusBar().addPermanentWidget(self.simulation_banner)
        self.simulation_banner.hide()
        self.simulation_mode.toggled.connect(self._simulation_changed)
'''))
    config = one(cls.body, '_config')
    ret = next(n for n in config.body if isinstance(n, ast.Return))
    if not isinstance(ret.value, ast.Call):
        raise ValueError('Unexpected GUI config builder')
    edits.append((ret.value.end_lineno - 1, ret.value.end_lineno - 1,
                  '            backend="simulation" if self.simulation_mode.isChecked() else "real",\n'))
    start = one(cls.body, '_start_worker')
    edits.append((body_start(start), body_start(start), '''        selected = "simulation" if self.simulation_mode.isChecked() else "real"
        if config.backend != selected:
            QMessageBox.warning(self, "Backend mismatch", "Select the matching backend before resuming this map.")
            return
'''))
    thread = [n for n in start.body if isinstance(n, ast.Assign) and any(ast.unparse(t) == 'self._thread' for t in n.targets)]
    if len(thread) != 1:
        raise ValueError('Cannot identify worker thread creation')
    edits.append((thread[0].lineno - 1, thread[0].lineno - 1,
                  '        self.simulation_mode.setEnabled(False)\n'))
    cleanup = one(cls.body, '_cleanup_worker')
    edits.append((body_start(cleanup), body_start(cleanup), '        self.simulation_mode.setEnabled(True)\n'))
    resume = one(cls.body, 'choose_resume')
    apply_calls = [n for n in resume.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                   and ast.unparse(n.value.func) == 'self._apply_config']
    if len(apply_calls) != 1:
        raise ValueError('Cannot identify resume config application')
    at = apply_calls[0].lineno - 1
    edits.append((at, at, '''        selected = "simulation" if self.simulation_mode.isChecked() else "real"
        if config.backend != selected:
            QMessageBox.warning(self, "Backend mismatch", "Select the matching real/simulation backend before choosing this checkpoint.")
            self._resume_directory = None
            return
'''))
    for name in ('connect_laser', 'turn_laser_on', 'turn_laser_off', 'set_laser_current'):
        method = one(cls.body, name)
        at = body_start(method)
        edits.append((at, at, '''        if self.simulation_mode.isChecked():
            self.set_status("SIMULATION — real laser controls are disabled")
            return
'''))
    toggle = one(cls.body, '_toggle_laser_controls')
    at = body_start(toggle)
    edits.append((at, at, '''        if getattr(self, "simulation_mode", None) is not None and self.simulation_mode.isChecked():
            self.laser_group.setEnabled(False)
            return
'''))
    status = one(cls.body, 'set_status')
    at = body_start(status)
    edits.append((at, at, '        if getattr(self, "simulation_mode", None) is not None and self.simulation_mode.isChecked():\n            text = "SIMULATION — " + text\n'))
    progress = one(cls.body, '_on_progress')
    titles = [n for n in progress.body if isinstance(n, ast.Assign) and any(ast.unparse(t) == 'title' for t in n.targets)]
    if len(titles) != 1:
        raise ValueError('Cannot identify progress title')
    at = titles[0].end_lineno
    edits.append((at, at, '        if self.simulation_mode.isChecked():\n            title = "SYNTHETIC — " + title\n'))
    edits.append((cls.end_lineno, cls.end_lineno, GUI_METHODS))
    return apply(source, edits)


ACQUISITION = Path('src/labtools/acquisition/intensity_map.py')
GUI = Path('src/labtools/gui/intensity_map_gui.py')
STATE = Path('.labtools-migrations/intensity-map-simulation-v1')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def laser_address():
    """Read the existing literal without importing its VISA dependencies."""
    path = Path('src/labtools/devices/itc4000.py')
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = one(tree.body, 'ITC4000')
    for node in cls.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == 'DEFAULT_ADDRESS' for t in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
        if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', '') == 'DEFAULT_ADDRESS':
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError('Cannot read existing ITC4000 DEFAULT_ADDRESS; nothing changed')


def plan():
    if not Path('pyproject.toml').is_file():
        raise ValueError('Run from the repository root containing pyproject.toml')
    changes = dict(PAYLOAD)
    for name in changes:
        if Path(name).exists():
            raise ValueError(f'New target already exists; refusing to overwrite: {name}')
    changes[str(ACQUISITION)] = patch_acquisition(ACQUISITION.read_text(encoding='utf-8-sig'))
    changes[str(GUI)] = patch_gui(GUI.read_text(encoding='utf-8-sig'))
    backend_path = 'src/labtools/simulation/map_backend.py'
    changes[backend_path] = changes[backend_path].replace(
        "'__INSTALLER_LASER_ADDRESS__'", repr(laser_address())
    )
    for name, text in changes.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
    # Static guard: native imports must not remain at module scope.
    for name in (str(ACQUISITION), str(GUI)):
        for node in ast.parse(changes[name]).body:
            if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('labtools.devices'):
                raise ValueError(f'Native device import remains at module scope: {name}')
    return {name: text.encode('utf-8') for name, text in changes.items()}


def rollback():
    manifest = STATE / 'manifest.json'
    records = json.loads(manifest.read_text(encoding='utf-8'))
    for name, record in records.items():
        path = Path(name)
        if not path.is_file() or digest(path.read_bytes()) != record['installed']:
            raise ValueError(f'Refusing to overwrite changed file: {name}')
    for name, record in records.items():
        path = Path(name)
        if record['original'] is None:
            path.unlink()
        else:
            path.write_bytes(bytes.fromhex(record['original']))
    manifest.unlink()
    print('[OK] Original files restored; no hardware opened')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if args.rollback:
        rollback()
        return
    manifest = STATE / 'manifest.json'
    if manifest.exists():
        raise ValueError('Simulation update already installed; do not apply twice')
    changes = plan()
    for name in changes:
        print('Update:', name)
    if args.check:
        print('[OK] Proposed Python files compile. No files changed or devices opened.')
        return
    originals = {name: Path(name).read_bytes() if Path(name).exists() else None for name in changes}
    records = {name: {'original': data.hex() if data is not None else None,
                      'installed': digest(changes[name])} for name, data in originals.items()}
    STATE.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(records, indent=2), encoding='utf-8')
    try:
        for name, data in changes.items():
            path = Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except BaseException:
        for name, data in originals.items():
            if data is None:
                Path(name).unlink(missing_ok=True)
            else:
                Path(name).write_bytes(data)
        manifest.unlink()
        raise
    print('[OK] Installed; no devices opened.')
    print('Backups:', STATE)
    print('Do not commit .labtools-migrations.')
    print('Test: uv run python -m pytest --noconftest tests/test_intensity_map_simulation.py -q')
    print('GUI: uv run python -m labtools.simulation.intensity_map --gui')


if __name__ == '__main__':
    main()
