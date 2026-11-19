"""Real Qt event/layout tests. Missing graphics libraries are skips, not acceptance."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def qt(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    try:
        from PyQt6 import QtCore, QtGui, QtTest, QtWidgets
    except ImportError as error:
        pytest.skip(f'Qt UI runtime unavailable: {error}')
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app, QtCore, QtGui, QtTest, QtWidgets


def wheel(qt, target, *, pixels=False):
    app, core, gui, _, _ = qt
    event = gui.QWheelEvent(core.QPointF(5, 5), core.QPointF(target.mapToGlobal(core.QPoint(5, 5))),
                           core.QPoint(0, -20) if pixels else core.QPoint(),
                           core.QPoint() if pixels else core.QPoint(0, -120),
                           core.Qt.MouseButton.NoButton, core.Qt.KeyboardModifier.NoModifier,
                           core.Qt.ScrollPhase.ScrollUpdate, False)
    app.sendEvent(target, event)


@pytest.mark.parametrize('kind', ['spin', 'double', 'combo', 'slider'])
@pytest.mark.parametrize('focused', [False, True])
def test_wheel_never_changes_parameter_but_keyboard_does(qt, kind, focused):
    app, core, _, test, widgets = qt
    from labtools.gui.operator_ui import protect_parameter_wheels
    root = widgets.QWidget()
    layout = widgets.QVBoxLayout(root)
    control = {'spin': widgets.QSpinBox, 'double': widgets.QDoubleSpinBox,
               'combo': widgets.QComboBox, 'slider': widgets.QSlider}[kind]()
    if kind == 'combo':
        control.addItems(['A', 'B', 'C'])
        control.setCurrentIndex(1)
        value = control.currentIndex
    else:
        control.setRange(0, 100)
        control.setValue(50)
        value = control.value
    layout.addWidget(control)
    protect_parameter_wheels(root)
    root.show()
    app.processEvents()
    if focused:
        control.setFocus()
    before = value()
    try:
        for pixels in [False, True]:
            wheel(qt, control, pixels=pixels)
            assert value() == before
        if isinstance(control, widgets.QAbstractSpinBox):
            wheel(qt, control.lineEdit())
            assert value() == before
        control.setFocus()
        test.QTest.keyClick(control, core.Qt.Key.Key_Up)
        assert value() != before
    finally:
        root.close()
        root.deleteLater()
        app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


def test_wheel_scrolls_parent_and_covers_late_camera_controls(qt):
    app, core, _, _, widgets = qt
    from labtools.gui.operator_ui import protect_parameter_wheels
    root = widgets.QWidget()
    layout = widgets.QVBoxLayout(root)
    scroll = widgets.QScrollArea()
    scroll.setWidgetResizable(True)
    layout.addWidget(scroll)
    content = widgets.QWidget()
    content.setMinimumHeight(2000)
    form = widgets.QVBoxLayout(content)
    spin = widgets.QSpinBox()
    spin.setValue(10)
    form.addWidget(spin)
    scroll.setWidget(content)
    protect_parameter_wheels(root)
    # Created after the guard, and in a separate owned top-level window.
    camera = widgets.QDialog(root)
    camera_layout = widgets.QVBoxLayout(camera)
    exposure = widgets.QDoubleSpinBox()
    exposure.setValue(20)
    camera_layout.addWidget(exposure)
    root.resize(500, 300)
    root.show()
    camera.show()
    app.processEvents()
    try:
        before = scroll.verticalScrollBar().value()
        wheel(qt, spin)
        assert spin.value() == 10
        assert scroll.verticalScrollBar().value() > before
        wheel(qt, exposure)
        assert exposure.value() == 20
    finally:
        camera.close()
        root.close()
        root.deleteLater()
        app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


def test_splitter_changes_orientation_both_ways(qt):
    app, core, _, _, widgets = qt
    from labtools.gui.operator_ui import ResponsiveSplitter
    splitter = ResponsiveSplitter()
    splitter.addWidget(widgets.QScrollArea())
    splitter.addWidget(widgets.QWidget())
    splitter.show()
    try:
        for width, orientation in [(1600, core.Qt.Orientation.Horizontal),
                                   (800, core.Qt.Orientation.Vertical),
                                   (1600, core.Qt.Orientation.Horizontal)]:
            splitter.resize(width, 700)
            app.processEvents()
            assert splitter.orientation() == orientation
            assert all(size > 0 for size in splitter.sizes())
    finally:
        splitter.close()
        splitter.deleteLater()
        app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)


@pytest.mark.parametrize('size', [(800, 600), (1024, 700), (1400, 900)])
def test_workspace_tabs_resize_and_keep_parameter_values(qt, tmp_path, monkeypatch, size):
    app, core, _, _, widgets = qt
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path / 'program'))
    monkeypatch.delenv('LABTOOLS_INSTRUMENT_PROFILE', raising=False)
    from labtools.gui.native_workspace import create_window
    from labtools.gui.operator_ui import ResponsiveSplitter
    from labtools.simulation.operator_session import SimulatedOperatorSession
    with SimulatedOperatorSession(ROOT / 'examples/workspace/working-lab/candidate.json',
                                  preferences_path=tmp_path / 'preferences.json',
                                  output_root=tmp_path / 'data', realtime=True) as session:
        window = create_window(session)
        window.resize(*size)
        window.show()
        try:
            app.processEvents()
            assert window.minimumWidth() == 800
            assert window.width() <= max(size[0], 800) and window.height() <= max(size[1], 600)
            assert window.mode_badge.text() == 'Simulation'
            assert not window.details_toggle.isChecked()
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                page = window.tabs.widget(index)
                assert page.width() <= window.width()
                for splitter in page.findChildren(ResponsiveSplitter):
                    if splitter.isVisible():
                        assert all(value > 0 for value in splitter.sizes())
                for control in page.findChildren(widgets.QAbstractSpinBox):
                    before = control.value()
                    wheel(qt, control)
                    assert control.value() == before
            window.open_camera()
            wheel(qt, window.camera_window.exposure_ms)
            assert window.camera_window.exposure_ms.value() == 20
        finally:
            window.close()
            app.processEvents()
            window.deleteLater()
            app.sendPostedEvents(None, core.QEvent.Type.DeferredDelete)
