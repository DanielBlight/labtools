"""Offline Analysis workspace. Workers load data; only the GUI thread draws."""
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from pathlib import Path
from threading import Event

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .exports import (
    export_collection,
    export_view,
    open_recipe,
    recipe,
    serialise,
    write_json,
)
from .loaders import LoadSession, read_json
from .models import AnalysisError
from .plotting import render
from .processing import PlotState

LABELS = {
    'group_view': 'Stack / sequence view', 'trend_metric': 'Trend metric',
    'trend_axis': 'Trend horizontal axis',
    'quantity': 'Map quantity', 'channel': 'Channel index (-1 = sum)',
    'cube_view': 'Hyperspectral map', 'variant': 'Spectrum/cube data',
    'low_nm': 'Lower wavelength (nm)', 'high_nm': 'Upper wavelength (nm)',
    'pixel_x': 'Pixel X index', 'pixel_y': 'Pixel Y index',
    'normalise': 'Normalisation', 'baseline': 'Baseline subtraction',
    'fit': 'Gaussian + constant fit', 'residuals': 'Show fit residuals',
    'comparison': 'Compare with reference', 'reference_key': 'Reference dataset',
    'cmap': 'Colour map', 'log': 'Log colour scale',
    'common': 'Common scale across loaded maps', 'vmin': 'Colour minimum (blank = auto)',
    'vmax': 'Colour maximum (blank = auto)', 'dpi': 'Export resolution (DPI)',
}
OPTIONS = {
    'group_view': ['overlay', 'trend'],
    'trend_metric': ['integral', 'mean', 'median', 'maximum', 'gradient_rms', 'centre_nm', 'fwhm_nm', 'area'],
    'trend_axis': ['index', 'cycle', 'cumulative_dwell_s', 'requested_dc_v'],
    'quantity': ['rates', 'counts', 'summed'],
    'cube_view': ['sum', 'area', 'band', 'wavelength', 'peak', 'peak_wavelength', 'fit_width', 'fit_area'],
    'variant': ['intensity', 'raw', 'dark', 'corrected'],
    'normalise': ['none', 'maximum', 'area'], 'baseline': ['none', 'linear', 'minimum'],
    'comparison': ['none', 'overlay', 'side-by-side', 'difference', 'ratio'],
    'cmap': ['inferno', 'viridis', 'magma', 'plasma', 'gray', 'coolwarm'],
}


class AnalysisToolbar(NavigationToolbar2QT):
    # All writes must go through the guarded Analysis export controls.
    toolitems = tuple(item for item in NavigationToolbar2QT.toolitems if item[0] != 'Save')


class AnalysisPanel(QWidget):
    """No workspace argument: analysis cannot acquire or reserve hardware."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='labtools-analysis-load')
        self.future = None
        self.cancel = Event()
        self.session = None
        self.root = self.node = self.source = None
        self.nodes = {}
        self.state = PlotState()
        self._closed = False
        self._recipe_job = False
        self._display_valid = False
        self._display_arrays = {}
        layout = QVBoxLayout(self)
        # Allow the existing narrow vertical layout to shrink below child size hints.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(8, 6, 8, 6)
        buttons = QGridLayout()
        for index, (text, callback) in enumerate([
            ('Open file', self.open_file), ('Open folder', self.open_folder),
            ('Open recipe', self.choose_recipe), ('Relink recipe source', self.relink_recipe),
            ('Cancel loading', self.cancel_load), ('Close dataset', self.close_dataset),
        ]):
            button = QPushButton(text)
            button.clicked.connect(callback)
            buttons.addWidget(button, index // 3, index % 3)
        layout.addLayout(buttons)
        self.status = QLabel('Offline Analysis | Open a saved result. No instruments are used.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)
        self.sidebar = QTabWidget()
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setUsesScrollButtons(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Dataset / step', 'Status'])
        self.tree.setMinimumWidth(0)
        self.tree.currentItemChanged.connect(self.selected)
        self.sidebar.addTab(self.tree, 'Datasets')
        control_widget = QWidget()
        form = QFormLayout(control_widget)
        self.control_form = form
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.controls = {}
        for field in fields(PlotState):
            name = field.name
            value = getattr(self.state, name)
            if name in OPTIONS or name == 'reference_key':
                control = QComboBox()
                if name in OPTIONS:
                    control.addItems(OPTIONS[name])
                    control.setCurrentText(str(value))
                else:
                    control.addItem('None', '')
            elif isinstance(value, bool):
                control = QCheckBox()
                control.setChecked(value)
            else:
                control = QLineEdit('' if value is None else str(value))
            control.setMinimumWidth(0)
            control.installEventFilter(self)
            control.setAccessibleName(LABELS[name])
            self.controls[name] = control
            form.addRow(LABELS[name], control)
        apply = QPushButton('Apply plot settings')
        apply.setObjectName('primaryButton')
        apply.clicked.connect(self.redraw)
        form.addRow(apply)
        reset = QPushButton('Reset processing and plot settings')
        reset.clicked.connect(self.reset_state)
        form.addRow(reset)
        note = QLabel('Raw data are read-only. Blank wavelength limits use the saved range. '
                      'Band view sums the selected range. Wavelength view uses the nearest saved sample to Lower wavelength. Channel is zero-based; -1 sums channels. '
                      'Focus metrics compare images, not absolute surface focus.')
        note.setWordWrap(True)
        form.addRow(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(control_widget)
        self.sidebar.addTab(scroll, 'Plot controls')
        self.metadata = QPlainTextEdit()
        self.metadata.setReadOnly(True)
        self.sidebar.addTab(self.metadata, 'Metadata / diagnostics')
        raw_widget = QWidget()
        raw_layout = QVBoxLayout(raw_widget)
        self.raw_array = QComboBox()
        self.raw_array.setAccessibleName('Raw array')
        self.raw_array.currentIndexChanged.connect(self.show_raw)
        raw_layout.addWidget(self.raw_array)
        raw_form = QFormLayout()
        raw_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.raw_row = QLineEdit('0')
        self.raw_column = QLineEdit('0')
        raw_form.addRow('Starting row (flattened leading axes)', self.raw_row)
        raw_form.addRow('Starting column (last axis)', self.raw_column)
        raw_layout.addLayout(raw_form)
        raw_button = QPushButton('Show raw array page (100 x 32)')
        raw_button.clicked.connect(self.show_raw)
        raw_layout.addWidget(raw_button)
        self.raw_table = QTableWidget()
        raw_layout.addWidget(self.raw_table, 1)
        self.sidebar.addTab(raw_widget, 'Raw arrays')
        self.splitter.addWidget(self.sidebar)
        plot = QWidget()
        plot_layout = QVBoxLayout(plot)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(9, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(0, 180)
        self.toolbar = AnalysisToolbar(self.canvas, self)
        plot_layout.addWidget(self.toolbar)
        plot_layout.addWidget(self.canvas, 1)
        self.splitter.addWidget(plot)
        self.splitter.setSizes([310, 750])
        self.canvas.mpl_connect('button_press_event', self.pick_pixel)
        self.canvas.mpl_connect('motion_notify_event', self.hover_pixel)
        exports = QGridLayout()
        for index, (text, callback) in enumerate([
            ('Export plot + data', self.export_current), ('Save plot recipe', self.save_recipe),
            ('Batch export measurements', self.batch_export),
        ]):
            button = QPushButton(text)
            button.clicked.connect(callback)
            exports.addWidget(button, index // 2, index % 2)
        layout.addLayout(exports)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(80)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel and isinstance(watched, QComboBox):
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        orientation = Qt.Orientation.Vertical if self.width() < 740 else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
        super().resizeEvent(event)

    def fail(self, error):
        self.status.setText(str(error))
        self.metadata.appendPlainText('\nDIAGNOSTIC\n' + traceback.format_exc())

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open saved Labtools data', '', 'Saved data (*.npz *.json *.csv)')
        if path:
            self.load_path(path)

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'Open result folder')
        if path:
            self.load_path(path)

    def cancel_load(self):
        self.cancel.set()
        if self.future is not None:
            self.status.setText('Cancelling load; the current dataset remains unchanged')

    def load_path(self, path):
        if self.future is not None:
            self.status.setText('A load is in progress. Cancel it before opening another dataset.')
            return
        self.cancel = Event()
        cancel = self.cancel
        def load():
            session = LoadSession(cancel.is_set)
            try:
                root = session.load(path)
                session.check()
                return session, root, Path(path).resolve()
            except BaseException:
                session.close()
                raise
        self._recipe_job = False
        self.future = self.executor.submit(load)
        self.status.setText('Loading saved data offline...')

    def choose_recipe(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open plot recipe', '', 'JSON (*.json)')
        if path:
            self.load_recipe(path)

    def relink_recipe(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose recipe to relink', '', 'JSON (*.json)')
        if path:
            try:
                document = read_json(path)
                if document.get('source_is_directory'):
                    source = QFileDialog.getExistingDirectory(self, 'Choose moved source folder')
                else:
                    source, _ = QFileDialog.getOpenFileName(self, 'Choose moved source file')
                if source:
                    self.load_recipe(path, source)
            except (OSError, ValueError) as error:
                self.fail(error)

    def load_recipe(self, path, source_override=None):
        if self.future is not None:
            self.status.setText('Finish or cancel the current load first')
            return
        self.cancel = Event()
        self._recipe_job = True
        self.future = self.executor.submit(open_recipe, path, source_override, self.cancel.is_set)
        self.status.setText('Verifying recipe source and loading...')

    def poll(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            result = future.result()
            if self.cancel.is_set():
                result[0].close()
                self.status.setText('Load cancelled')
                return
            if self._recipe_job:
                session, root, node, state, reference, source = result
                self.publish(session, root, source)
                self.state = state
                if reference is not None:
                    self.state.reference_key = reference.key
                self.write_controls()
                self.select_key(node.key)
                self.redraw()
            else:
                self.publish(*result)
        except Exception as error:  # noqa: BLE001 - GUI boundary reports malformed files without crashing
            self.fail(error)

    def publish(self, session, root, source):
        self.close_dataset()
        self.session, self.root, self.source = session, root, source
        self.nodes = {item.key: item for item in root.walk()}
        def add(node, parent=None):
            suffix = ' [SYNTHETIC]' if node.synthetic else ''
            item = QTreeWidgetItem([node.label + suffix, node.status])
            item.setData(0, Qt.ItemDataRole.UserRole, node.key)
            if parent is None:
                self.tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in node.children:
                add(child, item)
        add(root)
        self.tree.expandToDepth(1)
        self.controls['reference_key'].clear()
        self.controls['reference_key'].addItem('None', '')
        for item in root.walk():
            if item.kind != 'group':
                self.controls['reference_key'].addItem(item.label, item.key)
        self.state = PlotState()
        self.write_controls()
        self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.status.setText(f'Loaded {source.name}. Source files are read-only. '
                            + ('Some files could not be loaded; see diagnostics.' if session.diagnostics else ''))

    def select_key(self, key):
        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                self.tree.setCurrentItem(item)
                return True
            return any(visit(item.child(i)) for i in range(item.childCount()))
        for i in range(self.tree.topLevelItemCount()):
            if visit(self.tree.topLevelItem(i)):
                break

    def selected(self, current, previous=None):
        if current is None:
            return
        self.node = self.nodes[current.data(0, Qt.ItemDataRole.UserRole)]
        self.raw_array.blockSignals(True)
        self.raw_array.clear()
        self.raw_array.addItems(list(self.node.arrays))
        self.raw_array.blockSignals(False)
        self.raw_row.setText('0')
        self.raw_column.setText('0')
        self.show_raw()
        self.configure_controls()
        self.redraw()

    def configure_controls(self):
        kind = self.node.kind
        descendants = {item.kind for item in self.node.walk()}
        has_map = bool(descendants & {'map', 'cube'})
        has_spectrum = bool(descendants & {'spectrum', 'cube'})
        visibility = {
            'quantity': 'map' in descendants, 'channel': 'map' in descendants,
            'cube_view': 'cube' in descendants, 'variant': has_spectrum,
            'low_nm': has_spectrum, 'high_nm': has_spectrum,
            'pixel_x': kind == 'cube', 'pixel_y': kind == 'cube',
            'normalise': has_spectrum, 'baseline': has_spectrum,
            'fit': has_spectrum, 'residuals': kind in {'spectrum', 'cube'},
            'cmap': has_map, 'log': has_map, 'common': has_map,
            'vmin': has_map, 'vmax': has_map,
            'group_view': kind == 'group', 'trend_metric': kind == 'group', 'trend_axis': kind == 'group',
        }
        for name, visible in visibility.items():
            control = self.controls[name]
            control.setVisible(visible)
            label = self.control_form.labelForField(control)
            if label is not None:
                label.setVisible(visible)

    def read_controls(self):
        data = {}
        for field in fields(PlotState):
            name = field.name
            control = self.controls[name]
            if isinstance(control, QCheckBox):
                value = control.isChecked()
            elif isinstance(control, QComboBox):
                value = control.currentData() if name == 'reference_key' else control.currentText()
            else:
                text = control.text().strip()
                if name in {'channel', 'pixel_x', 'pixel_y', 'dpi'}:
                    try:
                        value = int(text)
                    except ValueError as error:
                        raise AnalysisError(f'{LABELS[name]} must be an integer') from error
                else:
                    try:
                        value = float(text) if text else None
                    except ValueError as error:
                        raise AnalysisError(f'{LABELS[name]} must be a number or empty') from error
            data[name] = value
        return PlotState.from_dict(data)

    def write_controls(self):
        for name, value in self.state.to_dict().items():
            control = self.controls[name]
            if isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, QComboBox):
                if name == 'reference_key':
                    control.setCurrentIndex(max(0, control.findData(value)))
                else:
                    control.setCurrentText(value)
            else:
                control.setText('' if value is None else str(value))

    def reset_state(self):
        self.state = PlotState()
        self.write_controls()
        self.redraw()

    def redraw(self):
        if self.node is None:
            return
        self._display_valid = False
        try:
            state = self.read_controls()
            reference = self.nodes.get(state.reference_key)
            arrays, details = render(self.figure, self.node, state, reference=reference, common_nodes=list(self.root.walk()))
            self.state = state
            self._display_arrays = arrays
            self._display_valid = True
            info = {'source': str(self.node.source), 'kind': self.node.kind, 'status': self.node.status,
                    'synthetic': self.node.synthetic, 'arrays': serialise(self.node.arrays),
                    'acquisition': serialise(self.node.metadata), 'display': details,
                    'diagnostics': self.session.diagnostics}
            self.metadata.setPlainText(json.dumps(info, indent=2, allow_nan=False))
            self.status.setText(('SYNTHETIC DATA | ' if self.node.synthetic else '') + self.node.label + ' | Raw arrays preserved')
        except Exception as error:  # noqa: BLE001 - keep invalid controls or corrupt data inside the Analysis panel
            self.figure.clear()
            axes = self.figure.add_subplot(111)
            axes.axis('off')
            axes.text(.05, .5, str(error), wrap=True, transform=axes.transAxes)
            self.fail(error)
        self.canvas.draw_idle()
        self.toolbar.update()

    def _pixel(self, event):
        if self.node is None or self.node.kind not in {'map', 'cube'} or not self.figure.axes:
            return None
        if event.inaxes is not self.figure.axes[0] or event.xdata is None or event.ydata is None:
            return None
        a = self.node.arrays
        ix = int(np.argmin(np.abs(a['x'] - event.xdata)))
        iy = int(np.argmin(np.abs(a['y'] - event.ydata)))
        return iy, ix

    def pick_pixel(self, event):
        pixel = self._pixel(event)
        if pixel is not None and not self.toolbar.mode:
            iy, ix = pixel
            self.controls['pixel_x'].setText(str(ix))
            self.controls['pixel_y'].setText(str(iy))
            if self.node.kind == 'cube':
                self.redraw()

    def hover_pixel(self, event):
        pixel = self._pixel(event)
        if pixel is not None:
            iy, ix = pixel
            a = self.node.arrays
            complete = bool(a['mask'][iy, ix])
            values = self._display_arrays.get('displayed_map')
            value = values[iy, ix] if values is not None else None
            value_text = f'{value:g}' if value is not None and np.isfinite(value) else 'Unavailable'
            self.status.setText(('SYNTHETIC | ' if self.node.synthetic else '')
                                + f'X={ix}, Y={iy} | {a["x"][ix]:g} V, {a["y"][iy]:g} V | Value: {value_text} | '
                                + ('Acquired' if complete else 'Not acquired'))

    def show_raw(self, *_args):
        self.raw_table.clear()
        self.raw_table.setRowCount(0)
        self.raw_table.setColumnCount(0)
        if self.node is None or self.raw_array.currentText() not in self.node.arrays:
            return
        try:
            values = self.node.arrays[self.raw_array.currentText()]
            width = values.shape[-1] if values.ndim else 1
            values = values.reshape(-1, width)
            row, column = int(self.raw_row.text()), int(self.raw_column.text())
            if not 0 <= row < values.shape[0] or not 0 <= column < width:
                raise AnalysisError('Raw array row or column is outside the saved array')
            page = values[row:row + 100, column:column + 32]
            self.raw_table.setRowCount(page.shape[0])
            self.raw_table.setColumnCount(page.shape[1])
            self.raw_table.setVerticalHeaderLabels([str(i) for i in range(row, row + page.shape[0])])
            self.raw_table.setHorizontalHeaderLabels([str(i) for i in range(column, column + page.shape[1])])
            for iy in range(page.shape[0]):
                for ix in range(page.shape[1]):
                    value = page[iy, ix]
                    text = str(value) if np.isfinite(value) else 'Missing / non-finite'
                    item = QTableWidgetItem(text)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.raw_table.setItem(iy, ix, item)
        except (ValueError, IndexError) as error:
            self.status.setText(str(error))

    def _export_ready(self):
        if self.node is None:
            raise AnalysisError('Open and select a dataset first')
        state = self.read_controls()
        if state != self.state or not self._display_valid:
            raise AnalysisError('Apply valid plot settings before exporting')
        return state

    def export_current(self):
        try:
            state = self._export_ready()
            destination = QFileDialog.getExistingDirectory(self, 'Choose export parent outside source folder')
            if destination:
                target = export_view(destination, self.root, self.node, state, self.source,
                                     reference=self.nodes.get(state.reference_key), common_nodes=list(self.root.walk()))
                self.status.setText(f'Exported PNG/SVG/PDF, NPZ/CSV, metadata and recipe to {target}')
        except Exception as error:  # noqa: BLE001 - export failures are recoverable GUI errors
            self.fail(error)

    def save_recipe(self):
        try:
            state = self._export_ready()
            path, _ = QFileDialog.getSaveFileName(self, 'Save plot recipe (new file only)', '', 'JSON (*.json)')
            if path:
                target = Path(path).resolve()
                source_dir = self.source if self.source.is_dir() else self.source.parent
                if target == source_dir or source_dir in target.parents:
                    raise AnalysisError('Save recipes outside the source acquisition folder')
                write_json(target, recipe(self.root, self.node, state, self.source, self.nodes.get(state.reference_key)))
                self.status.setText(f'Recipe saved: {target}')
        except Exception as error:  # noqa: BLE001 - report invalid paths or existing recipe without overwriting
            self.fail(error)

    def batch_export(self):
        try:
            state = self._export_ready()
            destination = QFileDialog.getExistingDirectory(self, 'Batch export parent outside source folder')
            if not destination:
                return
            target = export_collection(destination, self.root, self.node, state, self.source)
            self.status.setText(f'Batch exported with stack-wide numerical archive: {target}')
        except Exception as error:  # noqa: BLE001 - stop batch on first failure and retain completed unique exports
            self.fail(error)

    def close_dataset(self):
        self.figure.clear()
        self._display_arrays = {}
        self.raw_array.blockSignals(True)
        self.raw_array.clear()
        self.raw_array.blockSignals(False)
        self.raw_table.clear()
        self.tree.clear()
        self.nodes.clear()
        self.root = self.node = self.source = None
        self._display_valid = False
        if self.session is not None:
            self.session.close()
            self.session = None
        self.metadata.clear()
        self.canvas.draw_idle()

    def shutdown(self):
        if self.future is not None:
            self.cancel.set()
            self.status.setText('Cancelling Analysis load; close again after it finishes')
            return False
        if not self._closed:
            self.close_dataset()
            self.timer.stop()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self._closed = True
        return True

    def closeEvent(self, event):
        if self.shutdown():
            event.accept()
        else:
            event.ignore()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if urls:
            self.load_path(urls[0].toLocalFile())
            event.acceptProposedAction()


def main():
    import sys
    app = QApplication(sys.argv)
    panel = AnalysisPanel()
    panel.setWindowTitle('Labtools | Offline Analysis')
    panel.resize(1150, 780)
    panel.show()
    if len(sys.argv) > 1:
        panel.load_path(sys.argv[1])
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
