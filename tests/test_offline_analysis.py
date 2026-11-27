"""Offline analysis contracts against uploaded fixtures and native output writers."""
import ast
import base64
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from labtools.analysis.exports import export_view, open_recipe, recipe, write_json
from labtools.analysis.loaders import LoadSession, fingerprint
from labtools.analysis.models import AnalysisError, Dataset, LoadCancelled
from labtools.analysis.plotting import render
from labtools.analysis.processing import (
    MIRROR_ASPECT,
    PlotState,
    colour_limits,
    compare,
    fit_peak,
    map_comparison,
    map_values,
    metrics,
    spectrum_values,
)


@pytest.fixture(scope='module')
def examples(tmp_path_factory):
    root = tmp_path_factory.mktemp('analysis-examples')
    text = (Path(__file__).parent / 'fixtures/analysis_examples_bundle.txt').read_text()
    count = 0
    pattern = r'=== FILE: (.*?) ===\n=== SIZE: (\d+) ===\n=== SHA256: ([A-F0-9]+) ===\n=== ENCODING: BASE64 ===\n(.*?)\n=== END FILE ==='
    for name, size, digest, encoded in re.findall(pattern, text, re.DOTALL):
        data = base64.b64decode(encoded)
        assert len(data) == int(size)
        assert hashlib.sha256(data).hexdigest().upper() == digest
        path = root / name
        assert path.resolve().is_relative_to(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        count += 1
    assert count == 30
    return root


@pytest.fixture
def session():
    value = LoadSession()
    yield value
    value.close()


@pytest.mark.parametrize('folder,kind,count', [
    ('intensity-map-complete', 'map', 1), ('intensity-map-partial', 'map', 1),
    ('focus-stack', 'group', 5), ('spectrum', 'spectrum', 1),
    ('hyperspectral', 'cube', 1), ('anneal-sequence', 'group', 5),
    ('mixed-sequence-partial', 'group', 8),
])
def test_supplied_formats(examples, session, folder, kind, count):
    node = session.load(examples / folder)
    assert node.kind == kind
    assert len(list(node.walk())) == count
    assert all(item.synthetic for item in node.walk())
    assert not session.diagnostics


@pytest.mark.parametrize('folder', ['intensity-map-complete', 'intensity-map-partial', 'focus-stack', 'spectrum', 'hyperspectral', 'anneal-sequence', 'mixed-sequence-partial'])
def test_every_saved_measurement_renders(examples, session, folder):
    root = session.load(examples / folder)
    for node in root.walk():
        figure = Figure()
        arrays, details = render(figure, node, PlotState(), common_nodes=list(root.walk()))
        assert details['synthetic']
        assert isinstance(arrays, dict)
        figure.clear()


def test_focus_every_map_metadata_and_common_scale(examples, session):
    root = session.load(examples / 'focus-stack')
    maps = [item for item in root.walk() if item.kind == 'map']
    assert [item.metadata['requested_dc_v'] for item in maps] == [0, 20, 40, 60]
    limits = []
    for item in maps:
        figure = Figure()
        _, details = render(figure, item, PlotState(common=True), common_nodes=maps)
        limits.append(details['colour_limits'])
        assert figure.axes[0].get_aspect() == MIRROR_ASPECT == .75
    assert all(value == limits[0] for value in limits)


def test_partial_mask_not_zero(examples, session):
    node = session.load(examples / 'intensity-map-partial')
    values = map_values(node, PlotState(quantity='counts'))
    assert np.isnan(values[~node.arrays['mask']]).all()
    assert np.isfinite(values[node.arrays['mask']]).all()


@pytest.mark.parametrize('mode', ['sum', 'area', 'band', 'peak', 'peak_wavelength'])
def test_cube_derivations(examples, session, mode):
    node = session.load(examples / 'hyperspectral')
    values = map_values(node, PlotState(cube_view=mode, low_nm=710, high_nm=735))
    assert values.shape == (7, 9)
    assert np.isnan(values[-1, -2:]).all()
    assert np.isfinite(values[0]).all()
    if mode == 'peak_wavelength':
        assert np.nanmin(values) >= 710 and np.nanmax(values) <= 735


def test_cube_selected_spectrum_and_incomplete(examples, session):
    node = session.load(examples / 'hyperspectral')
    x, y = spectrum_values(node, PlotState(pixel_x=2, pixel_y=3))
    np.testing.assert_array_equal(y, node.arrays['intensity'][3, 2])
    assert len(x) == 161
    with pytest.raises(AnalysisError, match='not acquired'):
        spectrum_values(node, PlotState(pixel_x=8, pixel_y=6))


@pytest.mark.parametrize('normalise', ['none', 'maximum', 'area'])
@pytest.mark.parametrize('baseline', ['none', 'minimum', 'linear'])
def test_processing_does_not_mutate_source(examples, session, normalise, baseline):
    node = session.load(examples / 'spectrum')
    before = node.arrays['intensity'].copy()
    x, y = spectrum_values(node, PlotState(normalise=normalise, baseline=baseline))
    assert np.isfinite(y).all() and len(x) == len(y)
    np.testing.assert_array_equal(before, node.arrays['intensity'])
    assert not node.arrays['intensity'].flags.writeable


def test_raw_dark_corrected(examples, session):
    node = session.load(examples / 'spectrum')
    _, raw = spectrum_values(node, PlotState(variant='raw'))
    _, dark = spectrum_values(node, PlotState(variant='dark'))
    _, corrected = spectrum_values(node, PlotState(variant='corrected'))
    np.testing.assert_array_equal(corrected, raw - dark)


@pytest.mark.parametrize('state', [PlotState(vmin=2, vmax=1), PlotState(vmin=0, vmax=1, log=True), PlotState(vmin=1),
    PlotState(low_nm=800, high_nm=700), PlotState(dpi=0), PlotState(pixel_x=-1), PlotState(channel=-2),
    PlotState(vmin=float('nan'), vmax=1), PlotState(normalise='invalid')])
def test_invalid_controls(state):
    with pytest.raises(AnalysisError):
        state.validate()


def test_zero_ratio_and_nan():
    first = np.array([[1., 2., np.nan]])
    second = np.array([[0., 1., 3.]])
    result = compare(first, second, 'ratio')
    assert np.isnan(result[0, 0]) and result[0, 1] == 2 and np.isnan(result[0, 2])


def test_different_grids_rejected(examples, session):
    node = session.load(examples / 'intensity-map-complete')
    other = replace(node, arrays={**node.arrays, 'x': node.arrays['x'] + 1})
    with pytest.raises(AnalysisError, match='identical voltage'):
        map_comparison(node, other, PlotState(comparison='difference'))


def test_all_nan_and_log_diagnostics():
    with pytest.raises(AnalysisError, match='No finite'):
        colour_limits([np.array([[np.nan]])], PlotState())
    with pytest.raises(AnalysisError, match='No positive'):
        colour_limits([np.array([[-1.]])], PlotState(log=True))
    assert metrics(np.full((2, 2), np.nan))['mean'] is None


def test_fit_gaussian_and_residuals():
    pytest.importorskip('scipy')
    x = np.linspace(700, 740, 101)
    y = 12 + 500 * np.exp(-.5 * ((x - 720) / 3)**2)
    fitted, result = fit_peak(x, y)
    assert result['centre_nm'] == pytest.approx(720)
    assert result['fwhm_nm'] == pytest.approx(2.354820045 * 3)
    assert np.max(np.abs(fitted - y)) < .001
    with pytest.raises(AnalysisError):
        fit_peak(x, np.ones_like(x))


def test_fit_residual_visibility():
    pytest.importorskip('scipy')
    x = np.linspace(700, 740, 101)
    node = Dataset('fit', 'spectrum', Path('test'), {'wavelength': x, 'intensity': 12 + 500 * np.exp(-.5 * ((x - 720) / 3)**2)}).validate()
    figure = Figure()
    render(figure, node, PlotState(fit=True, residuals=False))
    assert len(figure.axes) == 1
    render(figure, node, PlotState(fit=True, residuals=True))
    assert len(figure.axes) == 2


def test_trend_saved_dwell_only(examples, session):
    root = session.load(examples / 'anneal-sequence')
    arrays, details = render(Figure(), root, PlotState(group_view='trend', trend_axis='cumulative_dwell_s'))
    np.testing.assert_array_equal(arrays['trend_x'], [2, 6, 12])
    assert len(details['trend']['excluded']) == 1  # Baseline has no saved cumulative dwell.


def test_focus_trend(examples, session):
    root = session.load(examples / 'focus-stack')
    arrays, _ = render(Figure(), root, PlotState(group_view='trend', trend_axis='requested_dc_v', trend_metric='gradient_rms'))
    np.testing.assert_array_equal(arrays['trend_x'], [0, 20, 40, 60])


def test_large_member_mapped_and_closed(examples):
    session = LoadSession(mmap_threshold=1)
    root = session.load(examples / 'hyperspectral')
    assert isinstance(root.arrays['intensity'], np.memmap)
    mapped = root.arrays['intensity']
    session.close()
    assert mapped._mmap.closed


def test_cancelled_load(examples):
    session = LoadSession(cancel=lambda: True)
    try:
        with pytest.raises(LoadCancelled):
            session.load(examples / 'hyperspectral')
    finally:
        session.close()


def test_native_retained_writer_roundtrip(tmp_path, session):
    from labtools.runtime.retained_results import export_retained
    result = {'status': 'stopped', 'retained_steps': [
        {'cycle': 0, 'role': 'baseline', 'result': {'wavelength_nm': np.arange(10.), 'intensity': np.arange(10.)}},
        {'cycle': 1, 'role': 'post-anneal', 'result': {'wavelength_nm': np.arange(10.), 'intensity': np.arange(10.) + 2}},
    ]}
    target = export_retained(tmp_path, result, settings={'backend': 'simulation'})
    root = session.load(target)
    spectra = [item for item in root.walk() if item.kind == 'spectrum']
    assert len(spectra) == 2 and all(item.synthetic for item in spectra)
    assert spectra[1].metadata['cycle'] == 1


def test_native_spectrum_embedded_metadata(tmp_path, session):
    path = tmp_path / 'spectrum.npz'
    np.savez(path, wavelength_nm=np.arange(10.), intensity=np.arange(10.), raw_intensity=np.arange(10.) + 3,
             metadata=json.dumps({'kind': 'spectrum', 'schema_version': 1, 'dark_mode': 'subtract', 'synthetic_data': True}))
    node = session.load(path)
    assert node.synthetic and 'raw' in node.arrays


def test_native_cube_metadata_and_legacy(tmp_path, session):
    path = tmp_path / 'cube.npz'
    np.savez(path, x_v=np.arange(2.), y_v=np.arange(3.), wavelength_nm=np.arange(4.), intensity=np.ones((3, 2, 4)),
             completed_mask=np.ones((3, 2), bool), metadata_json=json.dumps({'status': 'completed', 'provenance': {'backend': 'simulation'}}))
    assert session.load(path).synthetic
    legacy = tmp_path / 'spectral_cube.npz'
    np.savez(legacy, x_mirror=np.arange(2.), y_mirror=np.arange(3.), wavelength=np.arange(4.), cube=np.ones((3, 2, 4)))
    assert session.load(legacy).kind == 'cube'


def test_native_sequence_moved_absolute_output(tmp_path, session):
    folder = tmp_path / '0000-baseline'
    folder.mkdir()
    np.savez(folder / 'spectrum.npz', wavelength_nm=np.arange(5.), intensity=np.arange(5.))
    (tmp_path / 'sequence.json').write_text(json.dumps({'status': 'cancelled', 'steps': [
        {'cycle': 0, 'phase': 'Spectrum', 'role': 'baseline', 'status': 'completed', 'output': r'C:\old\0000-baseline'}]}))
    root = session.load(tmp_path)
    spectra = [n for n in root.walk() if n.kind == 'spectrum']
    assert len(spectra) == 1 and spectra[0].metadata['cycle'] == 0


@pytest.mark.parametrize('failure', ['corrupt', 'object', 'shape', 'axis', 'mask', 'missing'])
def test_bad_data(tmp_path, session, failure):
    path = tmp_path / 'bad.npz'
    if failure == 'corrupt':
        path.write_bytes(b'not an NPZ')
    elif failure == 'object':
        np.savez(path, values=np.array([{}], dtype=object))
    elif failure == 'missing':
        np.savez(path, unknown=np.arange(3))
    else:
        x = np.array([0., 0.]) if failure == 'axis' else np.arange(2.)
        np.savez(path, x_v=x, y_v=np.arange(2.), summed_count_rate_cps=np.ones((3, 2) if failure == 'shape' else (2, 2)),
                 completed_mask=np.ones((2, 2), dtype=int if failure == 'mask' else bool))
    with pytest.raises(AnalysisError):
        session.load(path)


def test_exports_recipe_roundtrip_and_immutability(tmp_path, examples, session):
    source = examples / 'spectrum'
    before = {p.name: fingerprint(p) for p in source.iterdir()}
    root = session.load(source)
    first = export_view(tmp_path, root, root, PlotState(dpi=72), source)
    second = export_view(tmp_path, root, root, PlotState(dpi=72), source)
    assert first != second
    assert {p.name for p in first.iterdir()} >= {'plot.png', 'plot.svg', 'plot.pdf', 'displayed_data.npz', 'spectrum.csv', 'recipe.json', 'plot_metadata.json'}
    restored, _root, node, state, ref, origin = open_recipe(first / 'recipe.json')
    try:
        assert node.kind == 'spectrum' and state.dpi == 72 and ref is None and origin == source
        np.testing.assert_array_equal(node.arrays['intensity'], root.arrays['intensity'])
    finally:
        restored.close()
    assert before == {p.name: fingerprint(p) for p in source.iterdir()}


def test_recipe_changed_source_refused(tmp_path, session):
    path = tmp_path / 'source.npz'
    np.savez(path, wavelength_nm=np.arange(5.), intensity=np.arange(5.))
    root = session.load(path)
    target = tmp_path / 'recipe.json'
    write_json(target, recipe(root, root, PlotState(), path))
    path.write_bytes(b'changed')
    with pytest.raises(AnalysisError, match='changed'):
        open_recipe(target)


def test_no_export_inside_source(examples, session):
    source = examples / 'spectrum'
    root = session.load(source)
    with pytest.raises(AnalysisError, match='outside'):
        export_view(source, root, root, PlotState(), source)


def test_bad_recipe(tmp_path):
    path = tmp_path / 'recipe.json'
    path.write_text('{')
    with pytest.raises(AnalysisError):
        open_recipe(path)
    path.write_text('{}')
    with pytest.raises(AnalysisError):
        open_recipe(path)


def test_no_hardware_import_boundary():
    code = '''
import sys
class BlockHardware:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pylablib', 'usb', 'u3', 'LabJackPython', 'horiba', 'pyvisa'} or fullname.startswith(('labtools.runtime', 'labtools.acquisition', 'labtools.drivers')):
            raise AssertionError('Hardware import: ' + fullname)
sys.meta_path.insert(0, BlockHardware())
from labtools.analysis import loaders, processing, plotting, exports
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_native_integration_does_not_add_analysis_to_acquisition_pages():
    path = Path(__file__).parents[1] / 'src/labtools/gui/native_workspace.py'
    source = path.read_text()
    ast.parse(source)
    assert 'self.tabs.addTab(self.analysis_panel, "Analysis")' in source
    assert 'self.pages["Analysis"]' not in source
    assert 'if not self.analysis_panel.shutdown():' in source


def test_retained_focus_no_progress_duplicates(tmp_path, session):
    from labtools.runtime.retained_results import export_retained
    result = {'x_values_v': np.arange(2.), 'y_values_v': np.arange(3.), 'counts': np.ones((2, 3, 2), dtype=int),
              'count_rates_cps': np.ones((2, 3, 2)), 'summed_count_rate_cps': np.ones((3, 2)),
              'completed_mask': np.ones((3, 2), dtype=bool), 'complete': True}
    target = export_retained(tmp_path, {'kind': 'multi-z-intensity-map', 'maps': [
        {'sweep': 0, 'requested_dc_v': 20, 'latest_progress': result, 'result': result},
        {'sweep': 1, 'requested_dc_v': 40, 'latest_progress': result, 'result': result}]})
    root = session.load(target)
    maps = [item for item in root.walk() if item.kind == 'map']
    assert len(maps) == 2
    assert [item.metadata['requested_dc_v'] for item in maps] == [20, 40]
    assert all(item.status == 'completed' for item in maps)


def test_sequence_baseline_difference(examples, session):
    root = session.load(examples / 'anneal-sequence')
    arrays, details = render(Figure(), root, PlotState(comparison='difference'))
    assert np.all(arrays['spectrum_0000_intensity'] == 0)
    assert 'pre-anneal' in details['baseline_reference']


def test_nearest_wavelength_map(examples, session):
    root = session.load(examples / 'hyperspectral')
    result = map_values(root, PlotState(cube_view='wavelength', low_nm=721.1))
    index = np.argmin(abs(root.arrays['wavelength'] - 721.1))
    np.testing.assert_array_equal(result[0], root.arrays['intensity'][0, :, index])


def test_recipe_relink_directory(tmp_path, session):
    import shutil
    source = tmp_path / 'old'
    source.mkdir()
    np.savez(source / 'spectrum.npz', wavelength_nm=np.arange(5.), intensity=np.arange(5.))
    root = session.load(source)
    path = tmp_path / 'recipe.json'
    write_json(path, recipe(root, root, PlotState(), source))
    session.close()
    moved = tmp_path / 'new'
    shutil.move(source, moved)
    restored, _root, node, _state, _ref, _source = open_recipe(path, moved)
    try:
        assert node.kind == 'spectrum'
    finally:
        restored.close()


def test_cube_fit_map_and_residuals():
    pytest.importorskip('scipy')
    x = np.linspace(700, 740, 101)
    y = 12 + 500 * np.exp(-.5 * ((x - 720) / 3)**2)
    cube = np.broadcast_to(y, (2, 2, y.size)).copy()
    cube[1, 1] = 0  # A measured flat spectrum cannot be fitted.
    node = Dataset('cube fit', 'cube', Path('test'), {'x': np.arange(2.), 'y': np.arange(2.),
        'wavelength': x, 'intensity': cube, 'mask': np.ones((2, 2), bool)}).validate()
    values = map_values(node, PlotState(cube_view='fit_width'))
    assert values[0, 0] == pytest.approx(2.354820045 * 3)
    assert np.isnan(values[1, 1])
    figure = Figure()
    arrays, details = render(figure, node, PlotState(fit=True, residuals=True))
    assert 'pixel_residual' in arrays and len(figure.axes) == 4  # Map, colourbar, spectrum, residual.
    _, details = render(Figure(), node, PlotState(cube_view='fit_area'))
    assert details['fit_map']['failed_acquired_pixels'] == 1


def test_native_csv_synthetic_comment(tmp_path, session):
    path = tmp_path / 'spectrum.csv'
    path.write_text('# SYNTHETIC DATA ONLY\nwavelength_nm,intensity\n700,10\n701,20\n')
    node = session.load(path)
    assert node.synthetic and node.kind == 'spectrum'


def test_native_map_csv(examples, session):
    node = session.load(examples / 'intensity-map-partial/intensity_map_points.csv')
    assert node.kind == 'map' and node.synthetic
    assert not node.arrays['mask'].all()
    assert np.isnan(map_values(node, PlotState())[~node.arrays['mask']]).all()


def test_native_anneal_csv(tmp_path, session):
    path = tmp_path / 'anneal_positions.csv'
    path.write_text('sequence,pass,y_index,x_index,x_voltage_v,y_voltage_v,elapsed_s\n1,1,0,0,0.1,0.2,0.3\n2,1,0,1,0.2,0.2,0.6\n')
    node = session.load(path)
    assert node.kind == 'anneal'
    arrays, details = render(Figure(), node, PlotState())
    assert details['recorded_positions'] == 2
    np.testing.assert_array_equal(arrays['elapsed_s'], [.3, .6])


def test_native_map_csv_columns(tmp_path, session):
    path = tmp_path / 'intensity_map_points.csv'
    path.write_text('x_index,y_index,x_voltage_v,y_voltage_v,channel_1_counts,channel_1_cps,summed_cps,timestamp_unix_s,session_id,complete\n0,0,0,0,20,200,200,1,1,True\n1,0,1,0,-1,nan,nan,nan,-1,False\n')
    node = session.load(path)
    assert node.kind == 'map' and node.arrays['counts'][0, 0, 0] == 20
    assert not node.arrays['mask'][0, 1]


def test_stack_numerical_export(tmp_path, examples, session):
    from labtools.analysis.exports import export_collection
    source = examples / 'focus-stack'
    root = session.load(source)
    target = export_collection(tmp_path, root, root, PlotState(common=True, dpi=72), source)
    index = json.loads((target / 'batch_index.json').read_text())
    assert len(index['measurements']) == 4
    assert index['state']['vmin'] is not None
    with np.load(target / 'stack_data.npz', allow_pickle=False) as data:
        assert len([name for name in data.files if name.endswith('_displayed_map')]) == 4


def test_windows_publish_retries_transient_permission_error(tmp_path, monkeypatch):
    from labtools.analysis import exports

    staging = tmp_path / ".staging"
    final = tmp_path / "published"
    staging.mkdir()
    (staging / "complete.txt").write_text("complete")
    original = Path.rename
    attempts = []

    def transient(path, target):
        attempts.append((path, target))
        if len(attempts) < 3:
            raise PermissionError("simulated Windows scanner lock")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", transient)
    monkeypatch.setattr(exports.time, "sleep", lambda _seconds: None)
    exports._publish_directory(staging, final)
    assert len(attempts) == 3
    assert (final / "complete.txt").read_text() == "complete"
    assert not staging.exists()


def test_windows_publish_helper_is_not_recursive():
    import ast
    import inspect

    from labtools.analysis import exports

    tree = ast.parse(inspect.getsource(exports._publish_directory))
    recursive = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_publish_directory"
    ]
    rename_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "rename"
    ]
    assert not recursive
    assert len(rename_calls) == 1


def test_recipe_replay_keeps_primary_and_reference_after_insertion(tmp_path):
    root_dir = tmp_path / 'collection'
    root_dir.mkdir()
    for i, name in enumerate(('b', 'c'), start=1):
        np.savez(root_dir / f'{name}.npz', wavelength_nm=[500., 501.], intensity=[i, i])
    original = LoadSession()
    try:
        root = original.load(root_dir)
        b, c = root.children
        path = tmp_path / 'recipe.json'
        write_json(path, recipe(root, b, PlotState(comparison='difference'), root_dir, c))
        np.savez(root_dir / 'a.npz', wavelength_nm=[500., 501.], intensity=[10, 10])
        restored, _root, node, _state, reference, _origin = open_recipe(path)
        try:
            assert (node.label, reference.label) == ('b', 'c')
        finally:
            restored.close()
    finally:
        original.close()


def test_background_and_linked_pixel_are_non_destructive(tmp_path, session, monkeypatch):
    from labtools.analysis import plotting

    x = np.arange(4.)
    background = np.array([3., 1., 5.])
    data = np.tile(background, (1, 4, 1))
    data[0, 3] += [1, -3, 5]
    path = tmp_path / 'cube.npz'
    np.savez(path, x_v=x, y_v=[0.], wavelength_nm=[500., 501., 502.], intensity=data,
             completed_mask=np.ones((1, 4), dtype=bool), metadata_json=json.dumps({
                 'provenance': {'dark_mode': 'pre_taken', 'reusable_dark_stage': 'pre_stitch'}}))
    node = session.load(path)
    state = PlotState(background_roi='0,2,0,0')
    figure = Figure()
    output, details = render(figure, node, state)
    np.testing.assert_array_equal(output['background_intensity'], background)
    np.testing.assert_array_equal(output['displayed_map'], [[0, 0, 0, 3]])
    assert details['colour_limits'] == [-3., 3.]
    assert 'pre-stitch' in figure._suptitle.get_text()
    monkeypatch.setattr(plotting, 'map_values', lambda *_args: pytest.fail('Map recomputed on click'))
    plotting.draw_cube_pixel(figure, node, replace(state, pixel_x=3), output, details)
    np.testing.assert_array_equal(output['pixel_intensity'], [1, -3, 5])
    np.testing.assert_array_equal(node.arrays['intensity'], data)


@pytest.mark.parametrize('model', ['Gaussian', 'Lorentzian', 'Voigt'])
def test_two_peak_fits(model):
    from scipy.special import voigt_profile

    x = np.linspace(500, 530, 301)
    centres = [508., 520.]

    def profile(delta):
        if model == 'Gaussian':
            return np.exp(-0.5 * (delta / 1.1)**2)
        if model == 'Lorentzian':
            return 1 / (1 + (delta / 1.1)**2)
        return voigt_profile(delta, 1.1, .7) / voigt_profile(0, 1.1, .7)

    y = 2 + 8 * profile(x - centres[0]) + 6 * profile(x - centres[1])
    state = PlotState(fit_model=model, fit_peaks=2, fit_centres='508,520', fit_component=2)
    fitted, details = fit_peak(x, y, state)
    np.testing.assert_allclose(fitted, y, atol=1e-5)
    assert details['centre_nm'] == pytest.approx(520.)
    assert len(details['components']) == 2
    assert details['components'][0]['centre_nm'] == pytest.approx(508.)


def test_calibration_sibling_and_comparison_guard(tmp_path, session):
    common = {'x_v': [0., 1.], 'y_v': [0.], 'completed_mask': np.ones((1, 2), bool)}
    np.savez(tmp_path / 'cube.npz', **common, wavelength_nm=[500., 501.], intensity=[[[-2., 1.], [3., 4.]]])
    np.savez(tmp_path / 'map.npz', **common, summed_count_rate_cps=[[5., 9.]])
    np.savez(tmp_path / 'dark.npz', wavelength_nm=[500., 501.], intensity=[2., 3.],
             segment_0_wavelength_nm=[500., 501.], segment_0_intensity=[2., 3.],
             metadata=json.dumps({'kind': 'dark', 'schema_version': 2, 'centres_nm': [500.5]}))
    root = session.load(tmp_path)
    nodes = {item.kind: item for item in root.children}
    assert set(nodes) == {'map', 'cube', 'calibration'}
    assert len(render(Figure(), nodes['calibration'], PlotState())[0]) == 4
    with pytest.raises(AnalysisError, match='matching measurement quantities'):
        render(Figure(), nodes['map'], PlotState(comparison='difference'), reference=nodes['cube'])
    figure = Figure()
    _, details = render(figure, nodes['cube'], PlotState(log=True))
    assert details['nonpositive_hidden_by_log'] == 1
    assert len(figure.axes[0].collections) == 2


def test_missing_baseline_rejected(tmp_path, session):
    np.savez(tmp_path / 'after.npz', wavelength_nm=[500., 501.], intensity=[1., 2.])
    (tmp_path / 'sequence.json').write_text(json.dumps({'steps': [
        {'role': 'post-anneal', 'status': 'complete', 'source': 'after.npz'}]}))
    node = session.load(tmp_path)
    with pytest.raises(AnalysisError, match='No unique recorded baseline'):
        render(Figure(), node, PlotState(comparison='difference'))


def test_partial_shared_region_trend(tmp_path, session):
    for name, mask, rates in [('a', [[True, True]], [[2., 100.]]),
                              ('b', [[True, False]], [[4., 0.]])]:
        np.savez(tmp_path / f'{name}.npz', x_v=[0., 1.], y_v=[0.],
                 completed_mask=mask, summed_count_rate_cps=rates)
    root = session.load(tmp_path)
    output, _ = render(Figure(), root, PlotState(group_view='trend', trend_metric='shared_mean'))
    np.testing.assert_array_equal(output['trend_y'], [2., 4.])
    np.testing.assert_array_equal(output['coverage'], [1., .5])


def test_export_cancel_does_not_publish(tmp_path, examples, session):
    source = examples / 'spectrum'
    node = session.load(source)
    with pytest.raises(AnalysisError, match='cancelled'):
        export_view(tmp_path, node, node, PlotState(), source, cancel=lambda: True)
    assert not list(tmp_path.iterdir())


def test_cube_fit_cancellation_between_pixels(tmp_path, session):
    pytest.importorskip('scipy')
    path = tmp_path / 'cube.npz'
    wavelength = np.linspace(500, 530, 31)
    signal = np.exp(-0.5 * ((wavelength - 515) / 2)**2)
    np.savez(path, x_v=[0., 1.], y_v=[0.], wavelength_nm=wavelength,
             intensity=np.tile(signal, (1, 2, 1)), completed_mask=[[True, True]])
    cube = session.load(path)
    checks = iter((False, True))
    with pytest.raises(AnalysisError, match='Fitted map cancelled'):
        map_values(cube, PlotState(cube_view='fit_area'), cancel=lambda: next(checks))
