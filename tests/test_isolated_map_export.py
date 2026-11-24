"""Acquisition PNG export must not touch the live GUI's Matplotlib state."""

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from PIL import Image

from labtools.visualisation.map_export import export_intensity_map_png


def test_real_child_writes_png_without_parent_rendering(tmp_path, monkeypatch):
    from matplotlib.figure import Figure
    def forbidden(*args, **kwargs):
        raise AssertionError('Parent process must not render acquisition PNG')
    monkeypatch.setattr(Figure, 'savefig', forbidden)
    target = tmp_path / 'map with spaces.png'
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(export_intensity_map_png, [-1, 1], [-1, 1], [[1, np.nan], [3, 4]],
            title='Synthetic test', output_path=target).result(timeout=30)
    with Image.open(target) as image:
        assert image.format == 'PNG' and image.width > 100 and image.height > 100
    assert not list(tmp_path.glob('.map-render-*'))


@pytest.mark.parametrize('mode', ['exit', 'timeout', 'missing'])
def test_renderer_failure_preserves_previous_png_and_numeric_outputs(tmp_path, monkeypatch, mode):
    from labtools.visualisation import map_export
    target = tmp_path / 'map.png'
    target.write_bytes(b'previous image')
    numeric = tmp_path / 'intensity_map_complete.npz'
    np.savez(numeric, counts=np.array([1, 2]))
    def request(payload, rendered):
        if mode != 'missing':
            raise RuntimeError('Injected child failure; numeric outputs remain saved')
    monkeypatch.setattr(map_export._renderer, 'request', request)
    with pytest.raises(RuntimeError, match='numeric outputs remain saved'):
        export_intensity_map_png([-1, 1], [-1, 1], [[1, 2], [3, 4]], title='test', output_path=target)
    assert target.read_bytes() == b'previous image'
    with np.load(numeric, allow_pickle=False) as data:
        assert np.array_equal(data['counts'], [1, 2])
    assert not list(tmp_path.glob('.map-render-*'))


def test_live_gui_draw_while_worker_exports_saved_map(window, tmp_path):
    from test_experiment_panels import spin
    app, widget, workspace = window
    from dataclasses import replace
    config = replace(workspace.workflows.map_config(), x_points=2, y_points=2,
        integration_time_s=.001, settle_time_s=0, save_results=True, output_root=tmp_path/'saved')
    panel = widget.pages['Sequences']
    widget.tabs.setCurrentWidget(panel)
    def acquire():
        with workspace._ownership.reserve('Intensity map'):
            return workspace.acquire_map(config)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(acquire)
        draws = 0
        def done():
            nonlocal draws
            panel.spectrum_axes.set_title('GUI render during isolated map export')
            panel.canvas.draw()
            draws += 1
            return future.done()
        spin(app, done)
        result = future.result()
    assert draws > 1 and result.complete
    assert (result.output_directory/'summed_intensity_map.png').is_file()
    assert (result.output_directory/'intensity_map_complete.npz').is_file()
    assert not list(result.output_directory.glob('.map-render-*'))


pytest_plugins = ['test_experiment_panels']


def test_renderer_reuses_child_and_restarts_after_exit(tmp_path):
    from labtools.visualisation.map_export import _renderer
    export_intensity_map_png([-1, 1], [-1, 1], [[1, 2], [3, 4]], title='first', output_path=tmp_path/'first.png')
    first = _renderer.process
    export_intensity_map_png([-1, 1], [-1, 1], [[4, 3], [2, 1]], title='second', output_path=tmp_path/'second.png')
    assert _renderer.process is first and first.poll() is None
    first.kill()
    first.wait()
    export_intensity_map_png([-1, 1], [-1, 1], [[1, 2], [3, 4]], title='restart', output_path=tmp_path/'restart.png')
    assert _renderer.process is not first
    assert (tmp_path/'restart.png').is_file()
    _renderer.close()
    assert _renderer.process is None


def test_child_protocol_eof_surfaces_failure_and_reaps(tmp_path, monkeypatch):
    import subprocess
    import sys

    from labtools.visualisation import map_export
    renderer = map_export._Renderer()
    original = subprocess.Popen
    def exit_child(command, **kwargs):
        return original([sys.executable, '-c', 'raise SystemExit(7)'], **kwargs)
    monkeypatch.setattr(map_export.subprocess, 'Popen', exit_child)
    with pytest.raises(RuntimeError, match='exited unexpectedly'):
        renderer.request(tmp_path/'input.npz', tmp_path/'output.png')
    assert renderer.process is None


def test_protocol_timeout_kills_and_reaps_child(tmp_path, monkeypatch):
    from queue import Empty

    from labtools.visualisation import map_export
    renderer = map_export._Renderer()
    class ImmediateTimeout:
        def __init__(self, **kwargs):
            pass
        def put(self, value):
            pass
        def get(self, *, timeout):
            assert timeout == 120
            raise Empty()
    monkeypatch.setattr(map_export, 'Queue', ImmediateTimeout)
    with pytest.raises(RuntimeError, match='timed out'):
        renderer.request(tmp_path/'input.npz', tmp_path/'output.png')
    assert renderer.process is None


def test_save_refresh_stops_after_workspace_close(window):
    app, widget, workspace = window
    controls = [widget.pages[name].save_retained_button._availability
                for name in ('Spectrum', 'Intensity map', 'Annealing')]
    assert all(control.timer.isActive() for control in controls)
    widget.close()
    assert workspace._closed
    for control in controls:
        control.refresh()
        assert not control.timer.isActive()
    app.processEvents()
