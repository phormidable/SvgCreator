# file_io.py
"""FileIO: filesystem and dialog operations for the main window —
export SVG, save/load project, load background image, show SVG code.

Pure serialisation lives in scene_io.py; this module only handles
paths, dialogs, and user-facing success/failure messages.
"""

import json

from pathlib import Path

from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QPlainTextEdit, QVBoxLayout
from PySide6.QtGui import QFont


USER_SHAPES_PATH = Path(__file__).resolve().parent.parent / "user_shape.txt"

class FileIO:
    def __init__(self, window):
        self.window = window
        self.scene = window.scene

    # ------------------------------------------------------------
    #  SVG export / preview
    # ------------------------------------------------------------
    def _has_colored_shapes(self) -> bool:
        return any(s.color is not None
                   for s in self.scene.shape_manager.shapes)

    def export_svg(self):
        self.window.log("export_svg")
        bordered = False
        if self._has_colored_shapes():
            bordered = self._ask_stroke_style()
        if bordered is None:
            return  # user cancelled

        filepath, _ = QFileDialog.getSaveFileName(self.window, "Save SVG", "", "SVG files (*.svg)")
        if not filepath:
            return
        try:
            svg = self.scene.generate_svg(bordered=bordered)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg)
            self.window.set_status(f"✅ Exported to {filepath}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error",f"Could not save file:\n{e}")

    def _ask_stroke_style(self):
        """Ask whether shaped curves should be stroked with a darker border
        (drawing-area style) or flat (same as the fill). Returns True/False,
        or None if the user cancelled."""
        box = QMessageBox(self.window)
        box.setWindowTitle("Export SVG")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("How should shaped curves be stroked?")
        box.setInformativeText(
            "Borders — a darker shade of the fill, like the drawing area.\n"
            "No borders (flat) — the fill color itself."
        )
        borders_btn = box.addButton("Borders", QMessageBox.ButtonRole.AcceptRole)
        flat_btn = box.addButton("No borders (flat)", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(flat_btn)  # matches previous behaviour
        box.exec()
        clicked = box.clickedButton()
        if clicked is borders_btn:
            return True
        if clicked is flat_btn:
            return False
        return None  # cancel or dialog closed

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

    def save_user_shape(self, name: str, tooltip: str, kind: str, curves) -> bool:
        """Append one shape entry to user_shape.txt (JSON lines)."""
        entry = {
            "name": name,
            "tooltip": tooltip,
            "kind": kind,
            "curves": [
                [[round(p.pos().x(), 3), round(p.pos().y(), 3)] for p in c.points]
                for c in curves
            ],
        }
        try:
            with open(USER_SHAPES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            QMessageBox.critical(self.window, "Error", f"Could not save shape:\n{e}")
            return False
        self.window.set_status(f"💾 Saved '{name}' to {USER_SHAPES_PATH.name}")
        return True