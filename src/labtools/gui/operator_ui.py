"""Shared workspace presentation. No device access or acquisition policy lives here."""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFormLayout,
    QLabel,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QWidget,
)

# One deliberately light instrument theme, including disabled/focus states.
# Point-sized text follows Qt's DPI scaling; no global application style mutation.
STYLE = """
QMainWindow, QDialog { background: #f4f6f8; }
QWidget { color: #243247; font-size: 10pt; }
QLabel#appTitle { font-size: 17pt; font-weight: 600; }
QLabel#pageTitle { font-size: 15pt; font-weight: 600; }
QLabel#sectionTitle { font-size: 11pt; font-weight: 600; }
QLabel#modeBadge { background: #e6eef8; color: #244d7a; border-radius: 4px; padding: 5px 10px; }
QLabel#plotMeta, QLabel#hintText { color: #58677a; }
QLabel#statusText { color: #36475d; padding: 3px 6px; }
QGroupBox, QFrame#plotPanel { background: white; border: 1px solid #d7dee7; border-radius: 6px; }
QGroupBox { margin-top: 10px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: 600; }
QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit {
    background: white; color: #243247; border: 1px solid #bac6d4; border-radius: 4px; padding: 4px;
    selection-background-color: #2463a6; selection-color: white;
}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border: 1px solid #2463a6; }
QPushButton { background: white; border: 1px solid #bac6d4; border-radius: 4px; padding: 6px 10px; }
QPushButton:hover { background: #edf3fa; border-color: #7f9dbf; }
QPushButton:pressed { background: #dbe8f6; }
QPushButton:focus, QToolButton:focus { border: 1px solid #2463a6; }
QPushButton#primary, QPushButton#primaryButton { background: #2463a6; color: white; border-color: #2463a6; }
QPushButton#primary:hover, QPushButton#primaryButton:hover { background: #1d528c; }
QPushButton:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    background: #edf0f4; color: #68788a; border-color: #d7dee7;
}
QToolButton#sectionToggle { border: none; background: transparent; font-weight: 600; padding: 4px 0; text-align: left; }
QTabWidget::pane { border: 1px solid #d7dee7; background: #f4f6f8; }
QTabBar::tab { background: #e9edf2; padding: 9px 16px; border: none; }
QTabBar::tab:selected { background: white; color: #174f8c; border-bottom: 2px solid #2463a6; }
QProgressBar { border: 1px solid #d7dee7; border-radius: 3px; background: #edf0f4; text-align: center; }
QProgressBar::chunk { background: #4b84bd; }
QScrollArea { border: none; background: transparent; }
QSplitter::handle { background: #e2e7ee; }
QCheckBox { spacing: 6px; }
"""


class ParameterWheelGuard(QObject):
    """Block wheel edits even with focus; scroll the surrounding form instead.

    Installed on the application but scoped to this window's QObject ancestry,
    including its owned camera/dialogs and widgets created after installation.
    """

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        node = watched
        parameter = False
        scroll = None
        in_scope = False
        while node is not None:
            if isinstance(node, (QAbstractSpinBox, QComboBox)) or isinstance(node, QAbstractSlider) and not isinstance(node, QScrollBar):
                parameter = True
            if isinstance(node, QAbstractScrollArea) and scroll is None:
                scroll = node
            if node is self.parent():
                in_scope = True
                break
            node = node.parent()
        if not in_scope or not parameter:
            return False
        if scroll is not None:
            bar = scroll.verticalScrollBar()
            delta = event.pixelDelta().y()
            if not delta:
                delta = round(event.angleDelta().y() / 120 * bar.singleStep() * 3)
            bar.setValue(bar.value() - delta)
        event.accept()
        return True


def protect_parameter_wheels(window):
    if not hasattr(window, '_parameter_wheel_guard'):
        guard = ParameterWheelGuard(window)
        QApplication.instance().installEventFilter(guard)
        window._parameter_wheel_guard = guard


class ResponsiveSplitter(QSplitter):
    """Two-pane workflow: controls beside the result, stacked on narrow windows."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setChildrenCollapsible(False)
        self.setHandleWidth(6)
        self._last_orientation = None

    def resizeEvent(self, event):
        if self.count() == 2:
            # Font metrics scale with desktop text settings as well as Qt DPI.
            threshold = max(960, self.fontMetrics().horizontalAdvance('M') * 90)
            orientation = Qt.Orientation.Vertical if self.width() < threshold else Qt.Orientation.Horizontal
            if orientation != self._last_orientation:
                self._last_orientation = orientation
                controls = self.widget(0)
                controls.setMinimumWidth(0)
                controls.setMaximumWidth(16777215 if orientation == Qt.Orientation.Vertical else 480)
                self.setOrientation(orientation)
                self.setStretchFactor(0, 0)
                self.setStretchFactor(1, 1)
                self.setSizes([max(160, self.height() // 2), max(180, self.height() // 2)]
                              if orientation == Qt.Orientation.Vertical else [420, max(320, self.width() - 426)])
        super().resizeEvent(event)


def polish_panel(panel, *, simulated=False):
    """Use shared styling when legacy standalone windows are embedded as tabs."""
    panel.setStyleSheet('')
    panel.setMinimumSize(0, 0)
    panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
    for label in panel.findChildren(QLabel):
        if label.objectName() in {'pageSubtitle', 'simulationNotice'} or label.objectName() == 'hintText' and label not in (
                getattr(panel, 'background_status', None), getattr(panel, 'estimate', None)):
            label.hide()
        elif label.objectName() == 'pageTitle':
            label.setText('Spectrum' if hasattr(panel, 'pre_taken_dark') else label.text())
        elif label.objectName() in {'plotMeta', 'statusText'}:
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    for form in panel.findChildren(QFormLayout):
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
    if simulated:
        for name in ('simulation_banner', 'simulation_mode', 'laser_light'):
            widget = getattr(panel, name, None)
            if widget is not None:
                widget.hide()
    # A permanently disabled confirmation in a gated native draft is not an
    # operator action. Hiding it does not alter its state or execution gate.
    confirm = getattr(panel, 'confirm', None)
    if confirm is not None and not confirm.isEnabled():
        confirm.hide()


def fit_initial_window(window):
    """Use available logical screen geometry, never a fixed desktop-sized window."""
    screen = window.screen()
    if screen is not None:
        available = screen.availableGeometry()
        window.resize(min(1400, max(480, available.width() - 64)),
                      min(920, max(360, available.height() - 80)))
