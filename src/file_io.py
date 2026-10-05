# file_io.py
"""FileIO: filesystem and dialog operations for the main window —
export SVG, save/load project, load background image, show SVG code.

Pure serialisation lives in scene_io.py; this module only handles
paths, dialogs, and user-facing success/failure messages.
"""

import json

from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                               QFileDialog, QMessageBox, QPlainTextEdit,
                               QVBoxLayout)
from PySide6.QtGui import QFont


class FileIO:
    def __init__(self, window):
        self.window = window
        self.scene = window.scene

    # ------------------------------------------------------------
    #  SVG export / preview
    # ------------------------------------------------------------
    def export_svg(self):
        self.window.log("export_svg")
        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Save SVG", "", "SVG files (*.svg)")
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.scene.generate_svg())
            self.window.set_status(f"✅ Exported to {filepath}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error",
                                 f"Could not save file:\n{e}")

    def show_svg_code_dialog(self):
        svg_string = self.scene.generate_svg()

        dialog = QDialog(self.window)
        dialog.setWindowTitle("SVG Code")
        dialog.resize(700, 500)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        code_edit = QPlainTextEdit()
        code_edit.setPlainText(svg_string)
        code_edit.setFont(QFont("Courier New", 10))
        code_edit.setReadOnly(True)
        layout.addWidget(code_edit)

        buttons = QDialogButtonBox()
        copy_btn = buttons.addButton("Copy to clipboard",
                                     QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(svg_string))
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()

    # ------------------------------------------------------------
    #  Project save / load
    # ------------------------------------------------------------
    def save_project(self):
        self.window.log("save_project")
        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Save Project", "", "Bezier Project (*.json);;All files (*)")
        if not filepath:
            return
        if not filepath.lower().endswith(".json"):
            filepath += ".json"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.scene.save_state(), f, indent=2)
            self.window.set_status(f"💾 Saved to {filepath}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error", f"Could not save file:\n{e}")

    def load_project(self):
        self.window.log("load_project")
        filepath, _ = QFileDialog.getOpenFileName(
            self.window, "Load Project", "", "Bezier Project (*.json);;All files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.scene.load_state(state)
            self.window.set_status(f"📂 Loaded from {filepath}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error", f"Could not load file:\n{e}")

    # ------------------------------------------------------------
    #  Background image
    # ------------------------------------------------------------
    def load_background_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self.window, "Open Background Image", "",
            "Images (*.png *.jpg *.jpeg *.svg);;All files (*)")
        if not filepath:
            return
        if self.scene.load_background_image(filepath):
            self.window.set_status(f"🖼️ Loaded background: {filepath}")
            self.window.refresh_preview_background()
        else:
            QMessageBox.warning(self.window, "Could not load", f"Failed to load image:\n{filepath}")