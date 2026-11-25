"""Qt acceptance contracts; skip explicitly when PyQt6 is unavailable."""
import importlib
import os
import time

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PyQt6')
QApplication = importlib.import_module('PyQt6.QtWidgets').QApplication
AnalysisPanel = importlib.import_module('labtools.analysis.gui').AnalysisPanel


@pytest.fixture
def panel():
    app = QApplication.instance() or QApplication([])
    widget = AnalysisPanel()
    widget.resize(1100, 760)
    widget.show()
    yield app, widget
    while widget.future is not None:
        app.processEvents()
        widget.poll()
        time.sleep(.005)
    widget.close()
    app.processEvents()


def spin(app, widget):
    deadline = time.monotonic() + 10
    while widget.future is not None:
        app.processEvents()
        widget.poll()
        assert time.monotonic() < deadline
        time.sleep(.005)
    app.processEvents()


def test_load_switch_narrow_and_invalid_controls(panel, tmp_path):
    app, widget = panel
    path = tmp_path / 'spectrum.npz'
    np.savez(path, wavelength_nm=np.arange(10.), intensity=np.arange(10.))
    widget.load_path(path)
    spin(app, widget)
    assert widget.node.kind == 'spectrum' and widget._display_valid
    widget.controls['dpi'].setText('not a number')
    widget.redraw()
    assert not widget._display_valid
    widget.reset_state()
    assert widget._display_valid
    widget.resize(480, 700)
    app.processEvents()
    assert widget.width() <= 600
    widget.close_dataset()
    assert widget.root is None


def test_failed_load_preserves_existing_dataset(panel, tmp_path):
    app, widget = panel
    path = tmp_path / 'spectrum.npz'
    np.savez(path, wavelength_nm=np.arange(10.), intensity=np.arange(10.))
    widget.load_path(path)
    spin(app, widget)
    original = widget.root
    widget.load_path(tmp_path / 'missing.npz')
    spin(app, widget)
    assert widget.root is original
