"""Read-only native workspace window. Never loads simulation panels or devices."""

from __future__ import annotations

import json
import sys


def create_window(workspace):
    # Kept lazy so headless launch requires neither Qt nor a display runtime.
    from PyQt6.QtWidgets import (
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    class NativeWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Labtools native workspace - execution disabled")
            self.resize(900, 700)
            body = QWidget()
            layout = QVBoxLayout(body)
            label = QLabel("NATIVE CANDIDATE: configuration inspection only. No hardware is opened.")
            label.setWordWrap(True)
            layout.addWidget(label)
            self.report = QPlainTextEdit()
            self.report.setReadOnly(True)
            layout.addWidget(self.report)
            self.refresh_button = QPushButton("Refresh source status (no device probe)")
            self.refresh_button.clicked.connect(self.refresh)
            layout.addWidget(self.refresh_button)
            self.operation_buttons = []
            for text in ("Connect devices", "Acquire map", "Acquire spectrum", "Capture dark"):
                button = QPushButton(text)
                button.setEnabled(False)
                button.setToolTip("Native execution has not been enabled in this candidate.")
                layout.addWidget(button)
                self.operation_buttons.append(button)
            close_button = QPushButton("Close workspace")
            close_button.clicked.connect(self.close)
            layout.addWidget(close_button)
            self.setCentralWidget(body)
            self.refresh()

        def refresh(self):
            try:
                data = workspace.describe()
            except (OSError, ValueError, RuntimeError) as error:
                self.report.setPlainText("Source status invalid; close and relaunch after correcting inputs.\n" + str(error))
            else:
                self.report.setPlainText(json.dumps(data, indent=2))

        def closeEvent(self, event):
            workspace.close()
            super().closeEvent(event)

    return NativeWindow()


def launch_window(workspace):
    from PyQt6.QtWidgets import QApplication

    if QApplication.instance() is not None:
        raise RuntimeError("Launch native workspace in its own process, not an existing Qt event loop")
    app = QApplication([sys.argv[0]])
    window = create_window(workspace)
    app.aboutToQuit.connect(workspace.close)
    window.show()
    return app.exec()
