"""Studio layout and synthetic laser regressions; no physical hardware access."""
from dataclasses import asdict
from pathlib import Path

import pytest

from labtools.gui.laser_model import LaserModel


def test_laser_connect_apply_on_off_disconnect_and_repeat():
    model = LaserModel(True)
    assert model.output is None
    for _ in range(2):
        model.execute('connect')
        assert model.output is False
        model.execute('apply', .060)
        assert model.current_a == .060 and model.output is False
        model.execute('on', .070)
        assert model.output is True and model.current_a == .070
        model.execute('connect')
        assert model.output is True  # Connect is not a hidden output-off action.
        model.execute('off')
        assert model.output is False
        model.execute('disconnect')
        assert model.output is None and not model.connected


@pytest.mark.parametrize('command', ['connect', 'apply', 'on', 'off', 'disconnect'])
def test_native_gate_precedes_state_changes(command):
    model = LaserModel(False)
    before = asdict(model)
    with pytest.raises(RuntimeError, match='disabled'):
        model.execute(command, .080)
    assert asdict(model) == before
    assert model.status == 'Laser: unknown'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), -.001, .101, True])
@pytest.mark.parametrize('command', ['apply', 'on'])
def test_bad_current_cannot_mutate_state(value, command):
    model = LaserModel(True)
    model.execute('connect')
    before = asdict(model)
    with pytest.raises(ValueError):
        model.execute(command, value)
    assert asdict(model) == before


@pytest.mark.parametrize('command', ['apply', 'on', 'off'])
def test_disconnected_actions_refused(command):
    model = LaserModel(True)
    with pytest.raises(RuntimeError, match='Connect'):
        model.execute(command, .080)
    assert model.output is None


def test_unknown_command_refused():
    model = LaserModel(True)
    with pytest.raises(ValueError):
        model.execute('invented')
    assert not model.connected


@pytest.fixture
def qt(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PyQt6 import QtCore, QtWidgets
    except ImportError as error:
        pytest.skip(f'QtWidgets unavailable: {error}')
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app, QtCore, QtWidgets


def test_laser_tab_buttons_and_header_indicator(qt):
    app, core, widgets = qt
    from labtools.gui.workspace_studio import LaserPanel
    indicator = widgets.QLabel()
    panel = LaserPanel(True, indicator)
    panel.show()
    try:
        panel.connect_button.click()
        panel.current.setValue(.065)
        panel.on_button.click()
        assert panel.model.output is True
        assert 'ON' in indicator.text() and 'simulated' in indicator.text()
        panel.off_button.click()
        assert panel.model.output is False
        panel.disconnect_button.click()
        assert panel.model.output is None
        assert 'disconnected' in indicator.text()
    finally:
        panel.close()
        panel.deleteLater()
        app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


def test_controls_grid_reflows_and_splitter_reflows(qt):
    app, core, widgets = qt
    from labtools.gui.workspace_studio import ControlGrid, StudioSplit
    grid = ControlGrid()
    for _ in range(4):
        grid.addWidget(widgets.QLabel('Control section'))
    grid.show()
    split = StudioSplit()
    split.addWidget(widgets.QWidget())
    split.addWidget(widgets.QWidget())
    split.show()
    try:
        for width, columns, orientation in [(1400, 2, core.Qt.Orientation.Horizontal),
                                             (800, 1, core.Qt.Orientation.Horizontal),
                                             (1400, 2, core.Qt.Orientation.Horizontal)]:
            grid.resize(width, 600)
            split.resize(width, 600)
            for _ in range(3):
                app.processEvents()
            assert grid.columns == columns
            assert split.orientation() == orientation
    finally:
        grid.close()
        split.close()
        grid.deleteLater()
        split.deleteLater()
        app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('size', [(800, 600), (1024, 700), (1400, 736)])
def test_full_workspace_views_and_retained_controls(qt, tmp_path, monkeypatch, size):
    app, core, widgets = qt
    from labtools.gui.native_workspace import create_window
    from labtools.simulation.operator_session import SimulatedOperatorSession
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path / 'program'))
    monkeypatch.delenv('LABTOOLS_INSTRUMENT_PROFILE', raising=False)
    root = Path(__file__).resolve().parents[1]
    with SimulatedOperatorSession(root / 'examples/workspace/working-lab/candidate.json',
                                  preferences_path=tmp_path / 'preferences.json',
                                  output_root=tmp_path / 'data', realtime=True) as session:
        window = create_window(session)
        window.resize(*size)
        window.show()
        try:
            assert window.tabs.tabText(window.tabs.count() - 1) == 'Laser'
            assert 'Camera' not in {window.tabs.tabText(i) for i in range(window.tabs.count())}
            assert window._studio_installed
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                for _ in range(3):
                    app.processEvents()
                assert window.minimumWidth() == 800
                assert window.width() <= max(size[0], 800) and window.height() <= max(size[1], 600)
                page = window.tabs.widget(index)
                if index:
                    assert not any(group.isVisible() and group.isCheckable()
                                   for group in page.findChildren(widgets.QGroupBox))
            anneal = window.pages['Annealing']
            window.tabs.setCurrentWidget(anneal)
            app.processEvents()
            assert not anneal.progress.isVisible()
            assert not any(bar.isVisible() for bar in anneal.findChildren(widgets.QProgressBar))
            assert anneal.x_points.isVisible() and anneal.x_points.isEnabled()
            mapping = window.pages['Intensity map']
            window.tabs.setCurrentWidget(mapping)
            app.processEvents()
            assert mapping.integration.isVisible()
            assert not mapping.laser_group.isVisible()
            mapping.use_second.setChecked(True)
            assert mapping.second_channel_widget.isVisible()
            spectrum = window.pages['Spectrum']
            window.tabs.setCurrentWidget(spectrum)
            app.processEvents()
            assert not spectrum.laser_group.isVisible()
            spectrum._studio_override.setChecked(True)
            assert spectrum.advanced_group.isChecked() and spectrum.gain_combo.isEnabled()
            window.laser_panel.connect_button.click()
            window.laser_panel.on_button.click()
            assert window.laser_panel.model.output is True
            window.stop_all_button.click()
            assert window.laser_panel.model.output is False
        finally:
            window.close()
            app.processEvents()
            window.deleteLater()
            app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)
