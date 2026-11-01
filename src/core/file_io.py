# core/file_io.py
"""FileIO: filesystem and dialog operations for the main window —
export SVG, save/load project, load background image, show SVG code.

Pure serialisation lives in scene_io.py; this module only handles
paths, dialogs, and user-facing success/failure messages.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QFileDialog, QMessageBox, QPlainTextEdit, QVBoxLayout
from PySide6.QtGui import QFont
from .settings import USER_SHAPES_PATH
from scene.scene_io import save_state



class FileIO:
    def __init__(self, window):
        self.window = window
        self.scene = window.scene
        self.json_dir = ""
        self.svg_dir = ""
        self.current_file = None

    # ------------------------------------------------------------
    #  Core helpers (reused by all save methods)
    # ------------------------------------------------------------
    def _write_json(self, filepath: Path) -> None:
        """Write the current state to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.scene.save_state(), f, indent=2)
        self.current_file = str(filepath)
        self.window.update_title()

    def _write_svg(self, filepath: Path, bordered: bool) -> None:
        """Generate and write the SVG to a file."""
        svg = self.scene.generate_svg(bordered=bordered)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(svg)

    def _get_bordered_style(self) -> bool | None:
        """Ask the user about stroke style if needed. Returns True/False/None."""
        if not self._has_colored_shapes():
            return False
        return self._ask_stroke_style()

    def _generate_unique_base_for_both(self, json_dir: Path, svg_dir: Path, base: str) -> str:
        """Return a unique base name that doesn't conflict in either directory."""
        candidate = base
        counter = 2
        while (json_dir / f"{candidate}.json").exists() or \
                (svg_dir / f"{candidate}.svg").exists():
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    # ------------------------------------------------------------
    #  SVG export / preview
    # ------------------------------------------------------------
    def _has_colored_shapes(self) -> bool:
        return any(s.color is not None
                   for s in self.scene.shape_manager.shapes)

    def export_svg(self):
        self.window.log("export_svg")
        bordered = self._get_bordered_style()
        if bordered is None:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self.window, "Save SVG", self.svg_dir, "SVG files (*.svg)")
        if not filepath:
            return
        path = Path(filepath)
        if path.suffix.lower() != ".svg":
            path = path.with_suffix(".svg")
        try:
            self._write_svg(path, bordered)
            self.svg_dir = str(path.parent)
            self.window.set_status(f"✅ Exported to {path}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error", f"Could not save file:\n{e}")

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
            self.window, "Save Project", self.json_dir,
            "Bezier Project (*.json);;All files (*)")
        if not filepath:
            return
        path = Path(filepath)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            self._write_json(path)
            self.json_dir = str(path.parent)
            self.window.set_status(f"💾 Saved to {path}")
        except Exception as e:
            QMessageBox.critical(self.window, "Error", f"Could not save file:\n{e}")

    def load_project(self):
        self.window.log("load_project")
        filepath, _ = QFileDialog.getOpenFileName(self.window, "Load Project", self.json_dir,"Bezier Project (*.json);;All files (*)")
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.scene.load_state(state)
            self.scene.undo.clear()
            self.json_dir = os.path.dirname(filepath)
            self.current_file = filepath  # NEW
            self.window.update_title()  # NEW
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
        """Append one shape entry to user_shape.txt (JSON lines), recentered
        on the shape's bounding-box centre so it can be placed anywhere."""
        points = [(p.model_pos().x(), p.model_pos().y()) for c in curves for p in c.points]
        cx = (min(x for x, _ in points) + max(x for x, _ in points)) / 2
        cy = (min(y for _, y in points) + max(y for _, y in points)) / 2

        entry = {
            "name": name,
            "tooltip": tooltip,
            "kind": kind,
            "curves": [
                [[round(p.model_pos().x() - cx, 3), round(p.model_pos().y() - cy, 3)] for p in c.points]
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

    def save_and_export(self, filepath: str):
        """Save both JSON and SVG with the same base filename."""
        path = Path(filepath)
        base = path.stem
        directory = path.parent

        bordered = self._get_bordered_style()
        if bordered is None:
            return

        json_path = directory / f"{base}.json"
        svg_path = directory / f"{base}.svg"

        errors = []

        try:
            self._write_json(json_path)
        except Exception as e:
            errors.append(f"JSON: {e}")

        try:
            self._write_svg(svg_path, bordered)
        except Exception as e:
            errors.append(f"SVG: {e}")

        if errors:
            QMessageBox.warning(self.window, "Partial save",
                               "Some files could not be saved:\n" + "\n".join(errors))
        else:
            self.window.set_status(f"💾 Saved {json_path.name} and {svg_path.name}")
            self.json_dir = str(directory)
            self.svg_dir = str(directory)

    def save_and_export_to_folders(self):
        """Save JSON and SVG to the configured directories."""
        if not self.json_dir and not self.svg_dir:
            QMessageBox.warning(self.window, "No directories configured",
                               "Please set JSON and SVG save directories in Settings.")
            return

        # Determine base name
        if self.current_file:
            base = Path(self.current_file).stem
        else:
            base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        json_dir = Path(self.json_dir) if self.json_dir else None
        svg_dir = Path(self.svg_dir) if self.svg_dir else None

        # Generate unique base for both directories
        unique_base = self._generate_unique_base_for_both(
            json_dir or Path("."), svg_dir or Path("."), base)

        errors = []

        # Save JSON
        if json_dir:
            json_path = json_dir / f"{unique_base}.json"
            try:
                self._write_json(json_path)
            except Exception as e:
                errors.append(f"JSON: {e}")

        # Save SVG
        if svg_dir:
            svg_path = svg_dir / f"{unique_base}.svg"
            try:
                bordered = self._get_bordered_style()
                if bordered is None:
                    bordered = True  # Default for auto-save
                self._write_svg(svg_path, bordered)
            except Exception as e:
                errors.append(f"SVG: {e}")

        if errors:
            QMessageBox.warning(self.window, "Partial save",
                               "Some files could not be saved:\n" + "\n".join(errors))
        else:
            self.window.set_status(f"💾 Auto-saved {unique_base}.json and {unique_base}.svg")