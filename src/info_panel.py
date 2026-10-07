# info_panel.py
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPlainTextEdit)
from PySide6.QtCore import Qt


class InfoPanel(QGroupBox):
    """Right-hand panel: curve selector and event console."""

    def __init__(self, scene, parent=None):
        super().__init__("Curves", parent)
        self.scene = scene
        self.updating_combobox = False

        outer = QVBoxLayout()
        outer.setSpacing(6)

        curve_row = QHBoxLayout()
        curve_label = QLabel("Curve:")
        curve_label.setFixedWidth(50)
        curve_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.curve_combo = QComboBox()
        self.curve_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.curve_combo.currentIndexChanged.connect(self.on_curve_selected)
        curve_row.addWidget(curve_label)
        curve_row.addWidget(self.curve_combo, 1)
        outer.addLayout(curve_row)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.console.setMaximumBlockCount(500)
        self.console.setPlaceholderText("Events will appear here…")
        self.console.setFixedHeight(120)
        outer.addWidget(self.console)

        self.setLayout(outer)

        scene.curveListChanged.connect(self.update_curve_combobox)
        scene.curveSelected.connect(self.on_scene_curve_selected)
        scene.messageLogged.connect(self.log)

        self.update_curve_combobox()

    def log(self, message: str):
        self.console.appendPlainText(message)

    def on_curve_selected(self, index):
        if self.updating_combobox:
            return
        self.scene.selected_curve_idx = index

    def on_scene_curve_selected(self, index):
        self.curve_combo.setCurrentIndex(index)

    def update_curve_combobox(self):
        if self.updating_combobox:
            return
        self.updating_combobox = True
        self.curve_combo.blockSignals(True)
        self.curve_combo.clear()
        for i in range(len(self.scene.curves)):
            self.curve_combo.addItem(self.scene.curves[i].name)
        if self.scene.curves:
            idx = self.scene.selected_curve_idx
            if idx < 0 or idx >= len(self.scene.curves):
                idx = len(self.scene.curves) - 1
            self.curve_combo.setCurrentIndex(idx)
        self.curve_combo.blockSignals(False)
        self.updating_combobox = False