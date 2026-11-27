"""Fresh operator views composed from existing controls, not new acquisition code."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from labtools.gui.laser_model import LaserModel

STYLE = """
QMainWindow, QDialog, QWidget#studioPage { background: #f1f3f5; color: #20282f; }
QWidget { color: #20282f; font-size: 8pt; }
QLabel#appTitle { font-size: 16pt; font-weight: 600; color: #182c30; }
QLabel#studioTitle { font-size: 14pt; font-weight: 600; }
QLabel#cardTitle { font-size: 9pt; font-weight: 600; color: #243d41; }
QLabel#modeBadge { background: #e1ecea; color: #23574f; padding: 3px 8px; border-radius: 4px; }
QFrame#studioCard { background: white; border: 1px solid #d9dfe2; border-radius: 7px; }
QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit {
    background: white; color: #20282f; border: 1px solid #b9c5ca;
    border-radius: 4px; padding: 1px 4px; selection-background-color: #16796f; selection-color: white;
}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus { border-color: #16796f; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    width: 0px; height: 0px; border: none;
}
QAbstractSpinBox { padding-right: 7px; }
QComboBox { padding-right: 6px; }

QPushButton { background: white; color: #253d41; border: 1px solid #b9c5ca; border-radius: 4px; padding: 3px 7px; }
QPushButton:hover { background: #edf5f3; border-color: #6a9d96; }
QPushButton:pressed { background: #d9eae6; }
QPushButton:focus { border-color: #16796f; }
QPushButton#primary, QPushButton#primaryButton { background: #16796f; color: white; border-color: #16796f; }
QPushButton#primary:hover, QPushButton#primaryButton:hover { background: #11645b; }
QPushButton:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    background: #edf0f2; color: #6d7c84; border-color: #d9dfe2;
}
QCheckBox { spacing: 6px; padding: 1px 0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #51636b; font-size: 12pt; font-weight: 400; padding: 7px 12px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #12665e; border-bottom: 2px solid #16796f; font-weight: 600; }
QTabBar::tab:hover { background: #e6eeec; }
QScrollArea { border: none; background: transparent; }
QStatusBar { background: #f1f3f5; border: none; }
QStatusBar::item { border: none; }
QSplitter::handle { background: transparent; }
QProgressBar { border: none; background: #e8eeec; border-radius: 3px; text-align: center; }
QProgressBar::chunk { background: #329386; border-radius: 3px; }
QToolBar { border: none; background: white; spacing: 4px; }
QToolButton { background: transparent; border: none; padding: 4px; }
QToolButton:hover { background: #e8f1ef; }
"""


def card(title):
    frame = QFrame()
    frame.setObjectName('studioCard')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(6)
    heading = QLabel(title)
    heading.setObjectName('cardTitle')
    layout.addWidget(heading)
    form = QFormLayout()
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setVerticalSpacing(3)
    layout.addLayout(form)
    return frame, form


def two_column_fields(items):
    widget = QWidget()
    grid = QGridLayout(widget)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(6)
    grid.setVerticalSpacing(3)
    for index, (label, control) in enumerate(items):
        row, column = divmod(index, 2)
        cell = QWidget()
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(1)
        cell_layout.addWidget(QLabel(label))
        cell_layout.addWidget(control)
        control.setMinimumWidth(64)
        control.setMaximumWidth(108)
        control.show()
        grid.addWidget(cell, row, column)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    return widget


def labelled_row(labels, widgets):
    result = QWidget()
    layout = QGridLayout(result)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(8)
    for i, (label, widget) in enumerate(zip(labels, widgets, strict=True)):
        layout.addWidget(QLabel(label), 0, i)
        enabled = widget.isEnabled()
        layout.addWidget(widget, 1, i)
        widget.setEnabled(enabled)
        widget.show()
        layout.setColumnStretch(i, 1)
        widget.setMinimumWidth(0)
    return result


def scroll_content():
    content = QWidget()
    content.setObjectName('studioPage')
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    scroll = QScrollArea()
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidgetResizable(True)
    content.setMinimumWidth(320)
    content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    scroll.setWidget(content)
    scroll.setMinimumWidth(0)
    scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setViewportMargins(0, 0, 0, 0)
    scroll.setStyleSheet('QScrollBar:vertical { width: 12px; margin: 0; }')
    return scroll, layout


class StudioSplit(QSplitter):
    """Stack narrow panes and remember the user split independently per orientation."""
    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(8)
        self._pane_sizes = {}

    def resizeEvent(self, event):
        if self.count() == 2:
            threshold = max(940, self.fontMetrics().horizontalAdvance('M') * 85)
            desired = Qt.Orientation.Vertical if event.size().width() < threshold else Qt.Orientation.Horizontal
            if self.orientation() != desired or not hasattr(self, '_studio_initialized'):
                current = self.orientation()
                if hasattr(self, '_studio_initialized'):
                    self._pane_sizes[current] = self.sizes()
                self._studio_initialized = True
                self.widget(0).setMaximumWidth(16777215)
                self.setOrientation(desired)
                self.setSizes(self._pane_sizes.get(desired, [350, 650] if desired == Qt.Orientation.Horizontal else [240, 360]))
        super().resizeEvent(event)


def new_page(panel, title):
    # Keep hidden legacy objects alive for references used by existing slots.
    old = panel.takeCentralWidget()
    old.setParent(panel)
    old.hide()
    panel._studio_legacy = old
    page = QWidget()
    page.setObjectName('studioPage')
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 14, 0, 0)
    layout.setSpacing(6)
    heading = QLabel(title)
    heading.setObjectName('studioTitle')
    layout.addWidget(heading)
    panel.setCentralWidget(page)
    panel.setMinimumSize(0, 0)
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    panel.statusBar().setSizeGripEnabled(False)
    panel.status.setMinimumWidth(0)
    panel.status.setWordWrap(True)
    panel.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
    panel.setStyleSheet('')
    return layout


def add_card(layout, title, rows):
    frame, form = card(title)
    for label, widget in rows:
        enabled = widget.isEnabled()
        if label is None:
            form.addRow(widget)
        else:
            form.addRow(label, widget)
        widget.setEnabled(enabled)
        widget.show()
    frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    layout.addWidget(frame)
    return frame


def actions(layout, panel, buttons):
    from PyQt6.QtWidgets import QHBoxLayout
    if hasattr(panel, 'estimate'):
        panel.estimate.setWordWrap(True)
        layout.addWidget(panel.estimate)
        panel.estimate.show()
    row = QHBoxLayout()
    row.setSpacing(6)
    for button in buttons:
        enabled = button.isEnabled()
        row.addWidget(button)
        button.setEnabled(enabled)
        button.show()
    layout.addLayout(row)


def result_view(panel):
    from labtools.gui.compact_plot import repair_plot_geometry
    frame = QFrame()
    frame.setObjectName('studioCard')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(4)
    if hasattr(panel, 'map_controller'):
        display = QFrame()
        display.setObjectName('plotControls')
        display_row = QHBoxLayout(display)
        display_row.setContentsMargins(4, 2, 4, 2)
        display_row.setSpacing(10)
        display_row.addWidget(QLabel('Display'))
        display_row.addWidget(panel.log_colour_scale)
        display_row.addWidget(panel.custom_colour_limits)
        panel.log_colour_scale.show()
        panel.custom_colour_limits.show()
        panel.colour_limits_widget.setVisible(panel.custom_colour_limits.isChecked())
        display_row.addWidget(panel.colour_limits_widget)
        display_row.addStretch(1)
        layout.addWidget(display)
    layout.addWidget(panel.toolbar)
    panel.toolbar.show()
    panel.canvas.setMinimumSize(160, 150)
    panel.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    repair_plot_geometry(panel)
    panel._studio_resize_connection = panel.canvas.mpl_connect(
        'resize_event', lambda event: repair_plot_geometry(panel))
    layout.addWidget(panel.canvas, 1)
    panel.canvas.show()
    panel.plot_meta.setMinimumWidth(0)
    panel.plot_meta.setWordWrap(True)
    panel.plot_meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout.addWidget(panel.plot_meta)
    panel.plot_meta.show()
    if hasattr(panel, 'map_controller'):
        panel.progress.setFixedHeight(14)
        layout.addWidget(panel.progress)
        panel.progress.show()
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return frame


def map_view(panel):
    layout = new_page(panel, 'Intensity map')
    split = StudioSplit()
    layout.addWidget(split, 1)
    controls = QWidget()
    control_layout = QVBoxLayout(controls)
    control_layout.setContentsMargins(0, 0, 0, 0)
    scroll, form_layout = scroll_content()
    control_layout.addWidget(scroll, 1)
    add_card(form_layout, 'Scan', [
        (None, two_column_fields([
            ('X start (V)', panel.x_start), ('Y start (V)', panel.y_start),
            ('X end (V)', panel.x_stop), ('Y end (V)', panel.y_stop),
            ('X points', panel.x_points), ('Y points', panel.y_points),
            ('Integration', panel.integration), ('Mirror settle', panel.settle),
        ])),
        (None, panel.serpentine),
    ])
    panel.time_controller_toggle.setChecked(True)
    add_card(form_layout, 'Counter', [
        ('Address', panel.address),
        (None, two_column_fields([
            ('Channel', panel.channel_1), ('Edge', panel.edge_1),
            ('Threshold', panel.threshold_1), ('', QWidget()),
        ])),
        (None, panel.use_second), (None, panel.second_channel_label), (None, panel.second_channel_widget)])
    panel.channel_1.setMinimumWidth(120)
    panel.edge_1.setMinimumWidth(120)
    panel._sync_second_channel_visibility()
    browse = QPushButton('Browse')
    browse.clicked.connect(panel._choose_output)
    output_card = add_card(form_layout, 'Output', [
        (None, QLabel('Folder')), (None, panel.output_root), (None, browse), (None, panel.save_results),
    ])
    output_card.findChild(QFormLayout).setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for widget in (panel.output_root, browse):
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    limits = QWidget()
    limits_form = QFormLayout(limits)
    limits_form.setContentsMargins(0, 0, 0, 0)
    limits_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    limits_form.addRow('Minimum', panel.colour_min)
    panel.colour_min.show()
    limits_form.addRow('Maximum', panel.colour_max)
    panel.colour_max.show()
    panel.colour_limits_widget = limits
    limits.hide()
    form_layout.addStretch(1)
    bottom = QWidget()
    bottom_layout = QVBoxLayout(bottom)
    bottom_layout.setContentsMargins(0, 0, 0, 0)
    bottom_layout.setSpacing(4)
    actions(bottom_layout, panel, [panel.start_button, panel.resume_button, panel.stop_button])
    control_layout.addWidget(bottom)
    split.addWidget(controls)
    split.addWidget(result_view(panel))
    panel.laser_group.hide()
    panel.laser_light.hide()


def spectrum_view(panel):
    layout = new_page(panel, 'Spectrum')
    split = StudioSplit()
    layout.addWidget(split, 1)
    controls = QWidget()
    control_layout = QVBoxLayout(controls)
    control_layout.setContentsMargins(0, 0, 0, 0)
    scroll, form_layout = scroll_content()
    control_layout.addWidget(scroll, 1)
    add_card(form_layout, 'Acquisition', [('Detector', panel.preset_combo),
        ('Start wavelength (nm)', panel.start_wl), ('End wavelength (nm)', panel.end_wl),
        ('Exposure', panel.exposure_box), ('Frames', panel.frames_box), ('Combine', panel.mode_combo)])
    override = QCheckBox('Override detector defaults')
    override.setChecked(panel.advanced_group.isChecked())
    override.toggled.connect(panel.advanced_group.setChecked)
    panel.advanced_group.toggled.connect(override.setChecked)
    panel._studio_override = override
    add_card(form_layout, 'Detector settings', [(None, override), ('Gain', panel.gain_combo),
        ('Readout', panel.speed_combo), ('Stitch overlap', panel.overlap_box), ('Entrance slit', panel.slit_width_box)])
    panel._update_advanced_controls()
    add_card(form_layout, 'Dark correction', [(None, panel.use_background), ('Source', panel.background_mode),
        ('Timing', panel.background_timing), (None, panel.capture_dark_button),
        (None, panel.load_dark_button), (None, panel.clear_dark_button), (None, panel.background_status)])
    add_card(form_layout, 'Output', [('Folder', panel.output_directory), (None, panel.output_browse_button),
        (None, panel.save_csv), (None, panel.save_png)])
    form_layout.addStretch(1)
    actions(control_layout, panel, [panel.connect_button, panel.acquire_button, panel.stop_button])
    split.addWidget(controls)
    split.addWidget(result_view(panel))
    panel.laser_group.hide()
    panel.laser_light.hide()


class ControlGrid(QWidget):
    """A controls-only page: two equal columns when space permits."""
    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.cards = []
        self.columns = 0

    def addWidget(self, widget):
        self.cards.append(widget)
        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        columns = 2 if self.width() >= max(1160, self.fontMetrics().horizontalAdvance('M') * 104) else 1
        if columns == self.columns and self.grid.count() == len(self.cards):
            return
        self.columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index, widget in enumerate(self.cards):
            self.grid.addWidget(widget, index // columns, index % columns,
                                Qt.AlignmentFlag.AlignTop)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)


def anneal_view(panel):
    layout = new_page(panel, 'Annealing')
    scroll, form_layout = scroll_content()
    layout.addWidget(scroll, 1)

    grid_widget = QWidget()
    grid = QGridLayout(grid_widget)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(12)
    form_layout.addWidget(grid_widget)

    scan_fields = two_column_fields([
        ('X start (V)', panel.x_start), ('Y start (V)', panel.y_start),
        ('X end (V)', panel.x_stop), ('Y end (V)', panel.y_stop),
        ('X points', panel.x_points), ('Y points', panel.y_points),
        ('Passes', panel.passes), ('Point dwell', panel.dwell),
        ('Mirror settle', panel.settle), ('', QWidget()),
    ])
    scan_card = add_card(grid, 'Scan', [
        (None, scan_fields),
        (None, panel.serpentine),
    ])

    right_stack = QWidget()
    right_layout = QVBoxLayout(right_stack)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(12)
    shutter_card = add_card(right_layout, 'Shutter', [
        ('Port', panel.sc10_port),
        (None, panel.test_sc10),
        (None, panel.shutter_state),
    ])
    right_layout.addStretch(1)
    power_card = add_card(right_layout, 'Power stage', [
        ('Anneal coordinate', panel.anneal_stage_coordinate),
        (None, panel.return_stage),
        ('Return coordinate', panel.return_stage_coordinate),
        (None, panel.test_stage),
        (None, panel.move_to_anneal_stage),
    ])

    browse = QPushButton('Browse')
    browse.clicked.connect(panel._browse_output)

    # A single spanning container prevents QFormLayout from assigning a narrow
    # label column to the path editor. The editor and Browse therefore receive
    # exactly the same horizontal geometry at every window width.
    output_card, output_form = card('Output')
    output_content = QWidget()
    output_layout = QVBoxLayout(output_content)
    output_layout.setContentsMargins(0, 0, 0, 0)
    output_layout.setSpacing(6)
    output_layout.addWidget(QLabel('Folder'))

    panel.output_root.setMinimumWidth(0)
    panel.output_root.setMaximumWidth(16777215)
    panel.output_root.setMinimumHeight(24)
    panel.output_root.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    panel.output_root.setVisible(True)
    output_layout.addWidget(panel.output_root)

    browse.setMinimumWidth(0)
    browse.setMaximumWidth(16777215)
    browse.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    output_layout.addWidget(browse)

    panel.save_log.setVisible(True)
    output_layout.addWidget(panel.save_log)
    output_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    output_form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    )
    output_form.addRow(output_content)
    grid.addWidget(output_card, 1, 0)

    grid.addWidget(scan_card, 0, 0)
    grid.addWidget(right_stack, 0, 1)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    grid.setRowStretch(0, 0)
    grid.setRowStretch(1, 0)
    scan_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    right_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    shutter_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    power_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    output_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

    form_layout.addStretch(1)
    actions(layout, panel, [panel.start_button, panel.stop_button])
    panel.progress.hide()  # Existing worker still updates its retained progress object.
    panel.open_camera_button.hide()


class LaserPanel(QWidget):
    def __init__(self, simulated, indicator, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QDoubleSpinBox
        self.model = LaserModel(simulated)
        self.indicator = indicator
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        title = QLabel('Laser')
        title.setObjectName('studioTitle')
        layout.addWidget(title)
        scroll, content = scroll_content()
        layout.addWidget(scroll, 1)
        self.current = QDoubleSpinBox()
        self.current.setRange(0, .100)
        self.current.setDecimals(3)
        self.current.setSuffix(' A')
        self.current.setValue(.080)
        self.connect_button = QPushButton('Connect')
        self.apply_button = QPushButton('Apply current')
        self.on_button = QPushButton('Output ON')
        self.off_button = QPushButton('Output OFF')
        self.disconnect_button = QPushButton('Disconnect')
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.note = QLabel('Simulated controls' if simulated else 'Native laser execution is disabled in this workspace candidate.')
        self.note.setWordWrap(True)
        controller_card = add_card(content, 'Controller', [(None, self.note), ('Drive current', self.current),
            (None, self.connect_button), (None, self.apply_button), (None, self.on_button),
            (None, self.off_button), (None, self.disconnect_button), (None, self.state)])
        controller_card.setMaximumWidth(640)
        content.addStretch(1)
        for button, command in [(self.connect_button, 'connect'), (self.apply_button, 'apply'),
                                (self.on_button, 'on'), (self.off_button, 'off'), (self.disconnect_button, 'disconnect')]:
            button.clicked.connect(lambda checked=False, cmd=command: self.command(cmd))
        self.update_state()

    def command(self, command):
        try:
            self.model.execute(command, self.current.value())
        except (ValueError, RuntimeError) as error:
            self.state.setText(str(error))
            return
        self.update_state()

    def update_state(self):
        model = self.model
        self.state.setText(model.status)
        self.indicator.setText('\u25cf ' + model.status)
        colour = '#9b6b20' if not model.simulated else ('#16796f' if model.output is True else '#687b82')
        self.indicator.setStyleSheet('color: ' + colour + '; padding: 4px 8px; font-weight: 600;')
        self.indicator.setAccessibleName(model.status)
        self.connect_button.setEnabled(model.simulated and not model.connected)
        for button in (self.apply_button, self.on_button, self.off_button, self.disconnect_button):
            button.setEnabled(model.simulated and model.connected)
        self.current.setEnabled(model.simulated)


def install_studio(window, workspace):
    """Rebuild views once, retaining all original worker/control signal wiring."""
    if getattr(window, '_studio_installed', False):
        return
    simulated = bool(getattr(workspace, 'simulation_only', False))
    window.setStyleSheet(STYLE)
    window.camera_window.setStyleSheet(STYLE)
    window.tabs.setMinimumSize(0, 0)
    window.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    window.centralWidget().setMinimumSize(0, 0)
    window.setMinimumSize(800, 600)
    window.tabs.setUsesScrollButtons(True)
    window.tabs.setElideMode(Qt.TextElideMode.ElideNone)
    mapping, spectrum, anneal = (window.pages[name] for name in ('Intensity map', 'Spectrum', 'Annealing'))
    map_view(mapping)
    spectrum_view(spectrum)
    anneal_view(anneal)
    window.laser_indicator = QLabel()
    window.laser_indicator.setToolTip('Laser state is independent of the annealing shutter and power stage.')
    header = window.centralWidget().layout().itemAt(0).layout()
    header.insertWidget(2, window.laser_indicator)
    if getattr(workspace, "all_hardware_enabled", False):
        from labtools.gui.hardware_laser_panel import HardwareLaserPanel

        window.laser_panel = HardwareLaserPanel(workspace, window.laser_indicator, window)
    else:
        window.laser_panel = LaserPanel(simulated, window.laser_indicator, window)
    window.tabs.addTab(window.laser_panel, 'Laser')
    if not getattr(workspace, "all_hardware_enabled", False):
        window.stop_all_button.clicked.connect(lambda: window.laser_panel.command('off')
            if window.laser_panel.model.connected else None)
    # Do not put a QWidget-only laser panel into pages: the legacy workflow
    # lifecycle helpers require their existing map/spectrum/anneal interfaces.
    window._studio_legacy_roots = [p._studio_legacy for p in (mapping, spectrum, anneal)]
    # Do not traverse/repolish all wrappers after reparenting. A child Qt
    # wrapper can already have a deleted C++ object during repeated construction.
    # The workspace stylesheet propagates safely from the live parent.
    for page in (mapping, spectrum):
        page.canvas.draw_idle()
    mapping.start_button.setText('Start map')
    mapping.resume_button.setText('Resume map')
    mapping.stop_button.setText('Stop')
    spectrum.stop_button.setText('Stop')
    anneal.stop_button.setText('Stop')
    finish_compact(window)
    window._studio_installed = True


def finish_compact(window):
    from PyQt6.QtWidgets import QAbstractButton, QComboBox, QLineEdit
    # Compact label/field rows instead of a label above every full-width field.
    for form in window.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(3)
    for widget in window.findChildren(QWidget):
        if isinstance(widget, QAbstractSpinBox):
            widget.setMinimumWidth(130)
            widget.setMaximumWidth(190)
        elif isinstance(widget, QComboBox):
            widget.setMinimumWidth(150)
            widget.setMaximumWidth(300)
            widget.setMinimumContentsLength(8)
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        elif isinstance(widget, QLineEdit):
            widget.setMinimumWidth(0)
        elif isinstance(widget, QAbstractButton):
            widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    mapping = window.pages['Intensity map']
    # Keep numeric fields compact without capping their cards.
    for control in (
        mapping.x_start, mapping.x_stop, mapping.x_points,
        mapping.y_start, mapping.y_stop, mapping.y_points,
        mapping.integration, mapping.settle,
    ):
        control.setMinimumWidth(0)
        control.setMaximumWidth(132)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    for control in (mapping.channel_1, mapping.edge_1):
        control.setMinimumWidth(0)
        control.setMaximumWidth(132)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    mapping.threshold_1.setMinimumWidth(0)
    mapping.threshold_1.setMaximumWidth(181)
    mapping.output_root.setMinimumWidth(0)
    mapping.output_root.setMaximumWidth(16777215)
    for form in mapping.centralWidget().findChildren(QFormLayout):
        if form.indexOf(mapping.output_root) >= 0:
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            break
    mapping.output_root.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    spectrum = window.pages['Spectrum']

    # Acquisition: preserve the working two-column arrangement.
    acquisition_form = next(
        (form for form in spectrum.findChildren(QFormLayout)
         if form.indexOf(spectrum.preset_combo) >= 0),
        None,
    )
    if acquisition_form is not None:
        acquisition_controls = (
            spectrum.preset_combo,
            spectrum.start_wl,
            spectrum.end_wl,
            spectrum.exposure_box,
            spectrum.frames_box,
            spectrum.mode_combo,
        )
        for control in acquisition_controls:
            taken = acquisition_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        acquisition_grid = two_column_fields([
            ('Detector', spectrum.preset_combo),
            ('Start wavelength (nm)', spectrum.start_wl),
            ('End wavelength (nm)', spectrum.end_wl),
            ('Exposure', spectrum.exposure_box),
            ('Frames', spectrum.frames_box),
            ('Combine', spectrum.mode_combo),
        ])
        for control in acquisition_controls:
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        acquisition_form.addRow(acquisition_grid)

    # Detector settings: one shared right edge despite the wider label column.
    detector_form = next(
        (form for form in spectrum.findChildren(QFormLayout)
         if form.indexOf(spectrum.gain_combo) >= 0),
        None,
    )
    if detector_form is not None:
        detector_controls = (
            spectrum.gain_combo,
            spectrum.speed_combo,
            spectrum.overlap_box,
            spectrum.slit_width_box,
        )
        detector_labels = ('Gain', 'Readout', 'Stitch overlap', 'Entrance slit')
        for control in detector_controls:
            taken = detector_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        detector_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        detector_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        detector_form.setHorizontalSpacing(8)
        detector_form.setVerticalSpacing(4)
        for label, control in zip(detector_labels, detector_controls, strict=True):
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            detector_form.addRow(label, control)

    dark_form = next(
        (form for form in spectrum.findChildren(QFormLayout)
         if form.indexOf(spectrum.background_mode) >= 0),
        None,
    )
    if dark_form is not None:
        dark_controls = (spectrum.background_mode, spectrum.background_timing)
        dark_labels = ('Source', 'Timing')
        for control in dark_controls:
            taken = dark_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        dark_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        dark_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        dark_form.setHorizontalSpacing(8)
        dark_form.setVerticalSpacing(4)
        for label, control in zip(dark_labels, dark_controls, strict=True):
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            dark_form.addRow(label, control)

    output_form = next(
        (form for form in spectrum.findChildren(QFormLayout)
         if form.indexOf(spectrum.output_directory) >= 0),
        None,
    )
    if output_form is not None:
        output_controls = (
            spectrum.output_directory,
            spectrum.output_browse_button,
            spectrum.save_csv,
            spectrum.save_png,
        )
        for control in output_controls:
            taken = output_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        output_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        output_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        output_form.setVerticalSpacing(4)
        for control in (spectrum.output_directory, spectrum.output_browse_button):
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        output_form.addRow('Folder', spectrum.output_directory)
        output_form.addRow('', spectrum.output_browse_button)
        output_form.addRow('', spectrum.save_csv)
        output_form.addRow('', spectrum.save_png)

    spectrum.acquire_button.setText('Acquire')
    for button in (spectrum.connect_button, spectrum.acquire_button, spectrum.stop_button):
        button.setMinimumWidth(0)
        button.setMaximumWidth(16777215)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    # Spectrum order/output refinement V2.
    # This runs after the existing Acquisition and Detector layout code and does
    # not replace either section.
    dark_form = next(
        (
            form
            for form in spectrum.findChildren(QFormLayout)
            if form.indexOf(spectrum.background_mode) >= 0
        ),
        None,
    )
    if dark_form is not None:
        dark_controls = (
            spectrum.background_mode,
            spectrum.background_timing,
            spectrum.capture_dark_button,
            spectrum.load_dark_button,
            spectrum.clear_dark_button,
            spectrum.background_status,
        )
        for control in dark_controls:
            taken = dark_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        dark_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        dark_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        dark_form.setHorizontalSpacing(8)
        dark_form.setVerticalSpacing(4)
        for label, control in (
            ('Source', spectrum.background_mode),
            ('Timing', spectrum.background_timing),
        ):
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            dark_form.addRow(label, control)
        for control in (
            spectrum.capture_dark_button,
            spectrum.load_dark_button,
            spectrum.clear_dark_button,
            spectrum.background_status,
        ):
            dark_form.addRow(control)

    output_form = next(
        (
            form
            for form in spectrum.findChildren(QFormLayout)
            if form.indexOf(spectrum.output_directory) >= 0
        ),
        None,
    )
    if output_form is not None:
        output_controls = (
            spectrum.output_directory,
            spectrum.output_browse_button,
            spectrum.save_csv,
            spectrum.save_png,
        )
        for control in output_controls:
            taken = output_form.takeRow(control)
            if taken.labelItem is not None and taken.labelItem.widget() is not None:
                taken.labelItem.widget().deleteLater()
        output_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        output_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        output_form.setHorizontalSpacing(8)
        output_form.setVerticalSpacing(4)
        for control in (spectrum.output_directory, spectrum.output_browse_button):
            control.setMinimumWidth(0)
            control.setMaximumWidth(16777215)
            control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        output_form.addRow(QLabel('Folder'))
        output_form.addRow(spectrum.output_directory)
        output_form.addRow(spectrum.output_browse_button)
        output_form.addRow(spectrum.save_csv)
        output_form.addRow(spectrum.save_png)
    # Annealing folder/spacing refinement V2.
    anneal = window.pages['Annealing']

    # Apply after generic widget normalization so the folder cannot collapse to
    # its text size under QFormLayout.FieldsStayAtSizeHint.
    anneal.output_root.setMinimumWidth(0)
    anneal.output_root.setMaximumWidth(16777215)
    anneal.output_root.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )

    shutter_form = next(
        (
            form
            for form in anneal.findChildren(QFormLayout)
            if form.indexOf(anneal.sc10_port) >= 0
        ),
        None,
    )
    power_form = next(
        (
            form
            for form in anneal.findChildren(QFormLayout)
            if form.indexOf(anneal.return_stage_coordinate) >= 0
        ),
        None,
    )
    # The right stack already contains a flexible spacer between Shutter and
    # Power stage. Increasing the card-internal spacing consumes that spacer,
    # so Power stage remains bottom-aligned with Scan.
    if shutter_form is not None:
        shutter_form.setVerticalSpacing(8)
    if power_form is not None:
        power_form.setVerticalSpacing(8)
    # Prominent header Camera action V2.
    # The header button is created in native_workspace.py as a local widget, so
    # locate it by its unique visible text instead of assuming window.camera_button.
    camera_button = next(
        (
            button
            for button in window.findChildren(QPushButton)
            if button.text() == 'Camera'
        ),
        None,
    )
    if camera_button is not None:
        camera_button.setObjectName('cameraAction')
        camera_button.setMinimumWidth(88)
        camera_button.setMinimumHeight(30)
        camera_button.setCursor(Qt.CursorShape.PointingHandCursor)
        camera_button.setToolTip('Open the camera preview and alignment tools')
        camera_button.setStyleSheet(
            "QPushButton#cameraAction {"
            " background: #16796f; color: white; border: 1px solid #11665e;"
            " border-radius: 4px; padding: 5px 14px; font-weight: 600; }"
            "QPushButton#cameraAction:hover { background: #116e65; }"
            "QPushButton#cameraAction:pressed { background: #0d5d56; }"
            "QPushButton#cameraAction:disabled {"
            " background: #c4d3d1; color: #6b777b; border-color: #aebdbc; }"
        )
    # Match Stop all dimensions to Camera.
    stop_all_button = next(
        (
            button
            for button in window.findChildren(QPushButton)
            if button.text() == 'Stop all'
        ),
        None,
    )
    if stop_all_button is not None:
        stop_all_button.setMinimumWidth(88)
        stop_all_button.setMinimumHeight(30)
        stop_all_button.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
    for page in window.pages.values():
        page.statusBar().setSizeGripEnabled(False)
    # Stage movement is an operational action, not buried in a scrolling card.
    anneal = window.pages['Annealing']
    root = anneal.centralWidget().layout()
    row = QHBoxLayout()
    row.addWidget(QLabel('Anneal coordinate'))
    old_form = next((form for form in anneal.findChildren(QFormLayout)
                     if form.indexOf(anneal.anneal_stage_coordinate) >= 0), None)
    if isinstance(old_form, QFormLayout):
        taken = old_form.takeRow(anneal.anneal_stage_coordinate)
        if taken.labelItem is not None and taken.labelItem.widget() is not None:
            taken.labelItem.widget().deleteLater()
    enabled = anneal.anneal_stage_coordinate.isEnabled()
    row.addWidget(anneal.anneal_stage_coordinate)
    anneal.anneal_stage_coordinate.setEnabled(enabled)
    anneal.anneal_stage_coordinate.show()
    enabled = anneal.move_to_anneal_stage.isEnabled()
    row.addWidget(anneal.move_to_anneal_stage)
    anneal.move_to_anneal_stage.setText('Move to anneal coordinate')
    anneal.move_to_anneal_stage.setEnabled(enabled)
    anneal.move_to_anneal_stage.show()
    row.addStretch(1)
    root.insertLayout(1, row)
    anneal.anneal_stage_coordinate.setMinimumWidth(200)
    anneal.anneal_stage_coordinate.setMaximumWidth(200)
    anneal.anneal_stage_coordinate.setMinimumHeight(28)
    anneal.move_to_anneal_stage.setMinimumWidth(190)
    anneal.move_to_anneal_stage.setMinimumHeight(28)
    # Compact the Laser tab into task rows instead of five full-width buttons.
    laser = window.laser_panel
    laser_layout = laser.layout()
    old_scroll = laser_layout.itemAt(1).widget()
    old_scroll.hide()
    laser_card, laser_form = card('Laser controller')
    laser_card.setMaximumWidth(620)
    laser_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    laser_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    for label, controls in [('Connection', [laser.connect_button, laser.disconnect_button]),
                            ('Current', [laser.current, laser.apply_button]),
                            ('Output', [laser.on_button, laser.off_button])]:
        task = QWidget()
        task_row = QHBoxLayout(task)
        task_row.setContentsMargins(0, 0, 0, 0)
        for control in controls:
            enabled = control.isEnabled()
            task_row.addWidget(control)
            control.setEnabled(enabled)
            control.show()
        task_row.addStretch(1)
        laser_form.addRow(label, task)
    laser_form.addRow(laser.note)
    laser.note.show()
    laser_form.addRow(laser.state)
    laser.state.show()
    laser_layout.addWidget(laser_card)
    laser_layout.addStretch(1)
    camera = window.camera_window
    camera.setStyleSheet(STYLE)
    camera.setMinimumSize(700, 520)
    camera.resize(1000, 700)
    for form in camera.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    for control in camera.findChildren(QAbstractSpinBox) + camera.findChildren(QComboBox) + camera.findChildren(QLineEdit):
        control.setMinimumWidth(0)
        control.setMaximumWidth(16777215)
        control.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    camera.start_button.setText('Start')
    camera.stop_button.setText('Stop')
    # Camera inherits the window stylesheet. Restrict only known live spin boxes.
    for widget in window.camera_window.findChildren(QAbstractSpinBox):
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
    window._studio_compact = True
