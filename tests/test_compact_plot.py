"""Rendering regression using real Agg canvas, including the existing colourbar topology."""
import time
from types import SimpleNamespace

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from labtools.gui.compact_plot import repair_plot_geometry


@pytest.mark.parametrize('size', [(10, 7), (4, 3), (2, 1.5), (12, 5)])
def test_existing_colourbar_repeated_draw_resize_and_update(size):
    figure = Figure(figsize=(10, 7), dpi=100)
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)
    image = axes.imshow(np.full((2, 2), np.nan), aspect='auto')
    bar = figure.colorbar(image, ax=axes, pad=.03)
    panel = SimpleNamespace(figure=figure, axes=axes, colourbar=bar)
    bar.ax.get_subplotspec().get_gridspec().set_height_ratios([0, 1, 0])
    figure.set_layout_engine('constrained')
    identities = tuple(map(id, figure.axes))
    for _ in range(3):
        figure.set_size_inches(*size)
        repair_plot_geometry(panel)
        image.set_data(np.arange(25).reshape(5, 5))
        image.set_clim(0, 24)
        bar.update_normal(image)
        canvas.draw()
        assert tuple(map(id, figure.axes)) == identities
        assert axes.get_position().width > 0 and bar.ax.get_position().height > 0
        assert np.array_equal(image.get_array(), np.arange(25).reshape(5, 5))


def test_spectrum_draw_without_layout_solver():
    figure = Figure(figsize=(5, 3))
    canvas = FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)
    axes.plot([600, 700, 800], [1, 3, 2])
    repair_plot_geometry(SimpleNamespace(figure=figure, ax=axes))
    canvas.draw()
    assert len(axes.lines) == 1


@pytest.mark.parametrize('size', [(800, 600), (1400, 736)])
def test_compact_workspace_camera_stage_and_map(tmp_path, monkeypatch, size):
    from pathlib import Path
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as error:
        pytest.skip(str(error))
    from labtools.gui.native_workspace import create_window
    from labtools.simulation.operator_session import SimulatedOperatorSession
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'local'))
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path/'program'))
    monkeypatch.delenv('LABTOOLS_INSTRUMENT_PROFILE', raising=False)
    root = Path(__file__).resolve().parents[1]
    with SimulatedOperatorSession(root/'examples/workspace/working-lab/candidate.json',
                                  preferences_path=tmp_path/'prefs.json',
                                  output_root=tmp_path/'data', realtime=True) as session:
        window = create_window(session)
        window.resize(*size)
        window.show()
        try:
            assert window._studio_compact
            window.open_camera()
            app.processEvents()
            assert window.camera_window.isVisible()
            assert window.camera_window.isWindow()
            assert window.camera_window.start_button.isVisible()
            assert window.camera_window.stop_button.isVisible()
            assert window.camera_window.surface.isVisible()
            camera = window.camera_window
            camera.start_button.click()
            deadline = time.monotonic() + 8
            while getattr(camera, '_last_packet', None) is None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            assert camera.busy and camera._last_packet is not None
            camera.stop_button.click()
            deadline = time.monotonic() + 8
            while camera.busy and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            assert not camera.busy
            assert camera._last_packet is not None  # Stop retains the last image.
            anneal = window.pages['Annealing']
            window.tabs.setCurrentWidget(anneal)
            app.processEvents()
            assert anneal.move_to_anneal_stage.isVisible()
            assert anneal.anneal_stage_coordinate.isVisible()
            mapping = window.pages['Intensity map']
            window.tabs.setCurrentWidget(mapping)
            for _ in range(3):
                app.processEvents()
            mapping.canvas.draw()
            mapping.image.set_data(np.arange(25).reshape(5, 5))
            mapping._refresh_colour_scale()
            mapping.canvas.draw()
            mapping.log_colour_scale.setChecked(True)
            mapping.canvas.draw()
            mapping.log_colour_scale.setChecked(False)
            mapping.canvas.draw()
            assert len(mapping.figure.axes) == 2
            assert mapping.axes.get_position().height > 0
        finally:
            if window.camera_window.busy:
                window.camera_window.request_stop()
                deadline = time.monotonic() + 8
                while window.camera_window.busy and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.005)
            assert not window.camera_window.busy
            window.close()
            app.processEvents()
            window.deleteLater()
