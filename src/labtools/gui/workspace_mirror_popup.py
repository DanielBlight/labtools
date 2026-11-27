"""Modeless source-bound mirror voltage popup, shared-workspace exclusion."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from labtools.gui.experiment_panels import TaskPanel, number
from labtools.gui.workspace_studio import card
from labtools.runtime.workspace_mirror import move_manual


class WorkspaceMirrorPopup(TaskPanel):
    def __init__(self, workspace, parent):
        super().__init__(workspace, "Mirror position")
        self.setParent(parent, Qt.WindowType.Window)
        self.setWindowTitle("Labtools | Mirror position")
        self.resize(440, 290)
        self.layout_root.setContentsMargins(14, 12, 14, 12)
        self.layout_root.setSpacing(8)
        self.right.setParent(self)
        self.right.hide()
        self.split.widget(0).setMinimumWidth(0)
        self.split.widget(0).setMaximumWidth(16777215)
        self.log.hide()
        self.log.setMaximumHeight(70)
        self.left.setSpacing(8)
        self.status.setWordWrap(True)
        source = workspace.plan.hardware_settings
        low = max(workspace.plan.map_config.safe_voltage_min_v, source["minimum_mirror_voltage_v"])
        high = min(workspace.plan.map_config.safe_voltage_max_v, source["maximum_mirror_voltage_v"])
        self.x = number(source["home_x_voltage_v"], low, high, 4)
        self.y = number(source["home_y_voltage_v"], low, high, 4)
        voltage_card, voltage_form = card("Commanded voltages")
        voltage_row = QWidget()
        voltage_layout = QGridLayout(voltage_row)
        voltage_layout.setContentsMargins(0, 0, 0, 0)
        voltage_layout.setHorizontalSpacing(10)
        voltage_layout.setVerticalSpacing(8)
        voltage_layout.addWidget(QLabel("X (V)"), 0, 0)
        voltage_layout.addWidget(self.x, 0, 1)
        voltage_layout.addWidget(QLabel("Y (V)"), 1, 0)
        voltage_layout.addWidget(self.y, 1, 1)
        voltage_layout.setColumnStretch(2, 1)
        voltage_layout.addWidget(self.start_button, 0, 3)
        voltage_layout.addWidget(self.stop_button, 1, 3)
        self.move_actions = voltage_layout
        voltage_form.addRow(voltage_row)
        self.controls.addWidget(voltage_card)
        self.home_button = QPushButton("Move to configured home")
        self.home_button.clicked.connect(self.home)
        self.controls.addWidget(self.home_button)
        note = QLabel("Commanded voltages, not readback.")
        note.setToolTip("Explicit movement only. Opening/closing sends no move. Each command closes its connection without homing. Stop cannot undo a completed DAC write. Use the reviewed beam setup; laser output is unchanged.")
        note.setWordWrap(True)
        self.controls.addWidget(note)
        self.controls.addStretch(1)
        # The inherited action row is empty after moving its buttons into the card.
        self.move_row = self.left.takeAt(1).layout()
        self.start_button.setText("Move X/Y")
        # Use one shared size and grid row for each input/action pair.
        paired_controls = (self.x, self.y, self.start_button, self.stop_button)
        for control in paired_controls:
            control.ensurePolished()
        control_width = max(control.sizeHint().width() for control in paired_controls)
        control_height = max(control.sizeHint().height() for control in paired_controls)
        for control in paired_controls:
            control.setMinimumSize(control_width, control_height)
        self.start_button.clicked.connect(self.move)
        self.save_result_button.hide()
        self.hide()

    def move(self):
        if self.busy:
            return
        x, y = self.x.value(), self.y.value()
        try:
            from labtools.runtime.workspace_mirror import validate_position

            validate_position(self.workspace, x, y)
            def run():
                with self.batch.borrow("Spectrum"), self.batch.borrow("Intensity map"):
                    return move_manual(self.workspace, x, y, stop=self.stop_event)
            self.launch(run, ("Spectrum", "Intensity map"))
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))

    def home(self):
        if self.busy:
            return
        source = self.workspace.plan.hardware_settings
        self.x.setValue(source["home_x_voltage_v"])
        self.y.setValue(source["home_y_voltage_v"])
        self.move()

    def completed(self, result):
        self.status.setText(f"Last commanded X={result['x_voltage_v']:g} V, Y={result['y_voltage_v']:g} V; not readback")
        self.log.appendPlainText(self.status.text())


def install_mirror_popup(window, workspace):
    popup = WorkspaceMirrorPopup(workspace, window)
    from labtools.gui.operator_ui import fit_initial_window

    popup.setStyleSheet(window.styleSheet())
    fit_initial_window(popup, preferred=(440, 290))
    window.mirror_window = popup
    window.pages["Mirror position"] = popup
    window.mirror_button = QPushButton("Mirror")
    window.mirror_button.setToolTip("Open manual mirror voltage positioning")
    camera = window.camera_button
    button = window.mirror_button
    button.setObjectName("mirrorAction")
    button.setStyleSheet(camera.styleSheet().replace("#cameraAction", "#mirrorAction"))
    button.setFont(camera.font())
    button.setCursor(camera.cursor())
    button.ensurePolished()
    camera.ensurePolished()
    size = camera.sizeHint().expandedTo(button.sizeHint()).expandedTo(camera.minimumSize())
    for action in (camera, button):
        action.setFixedSize(size)
        action.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    def show():
        popup.show()
        popup.raise_()
        popup.activateWindow()
    window.mirror_button.clicked.connect(show)
    # Header is a nested layout; locate the layout actually containing Camera.
    for layout in window.findChildren(QHBoxLayout):
        index = layout.indexOf(window.camera_button)
        if index >= 0:
            layout.insertWidget(index + 1, window.mirror_button)
            break
    else:
        raise RuntimeError("Camera header layout not found")
