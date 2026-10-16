# ui/info_panel.py
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QPlainTextEdit)
from PySide6.QtCore import Qt
from core.settings import CONSOLE_HEIGHT

class InfoPanel(QGroupBox):
    """Right-hand panel: curve selector and event console."""

    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.scene = scene

        outer = QVBoxLayout()
        outer.setSpacing(6)


        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.console.setMaximumBlockCount(500)
        self.console.setPlaceholderText("Events will appear here…")
        self.console.setFixedHeight(CONSOLE_HEIGHT)
        outer.addWidget(self.console)

        self.setLayout(outer)
        scene.messageLogged.connect(self.log)

    def log(self, message: str):
        self.console.appendPlainText(message)

