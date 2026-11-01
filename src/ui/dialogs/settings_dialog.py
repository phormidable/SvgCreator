from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                                QLabel, QLineEdit, QPushButton, QSpinBox,
                                QFileDialog, QColorDialog, QDialogButtonBox)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

class SettingsDialog(QDialog):
    """Unified dialog for all app settings."""

    def __init__(self, settings: dict, parent=None):
        """
        settings: dict with keys:
            - canvas_width, canvas_height (int)
            - stroke_width (int)
            - curve_color (QColor or str)
            - background_path (str or None)
            - json_dir (str)
            - svg_dir (str)
        """
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(550, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        # ---- Canvas size ----
        canvas_row = QHBoxLayout()
        self.canvas_w = QSpinBox()
        self.canvas_w.setRange(100, 2000)
        self.canvas_w.setValue(settings["canvas_width"])
        self.canvas_w.setSuffix(" px")
        self.canvas_h = QSpinBox()
        self.canvas_h.setRange(100, 2000)
        self.canvas_h.setValue(settings["canvas_height"])
        self.canvas_h.setSuffix(" px")
        canvas_row.addWidget(self.canvas_w)
        canvas_row.addWidget(QLabel("×"))
        canvas_row.addWidget(self.canvas_h)
        canvas_row.addStretch()
        form.addRow("Canvas size:", canvas_row)

        # ---- Stroke size ----
        self.stroke_spin = QSpinBox()
        self.stroke_spin.setRange(1, 5000)
        self.stroke_spin.setValue(settings["stroke_width"])
        self.stroke_spin.setSuffix(" units")
        form.addRow("Stroke size:", self.stroke_spin)

        # ---- Curve color ----
        color_row = QHBoxLayout()
        initial_color = settings["curve_color"]
        if isinstance(initial_color, str):
            initial_color = QColor(initial_color)
        self.color_edit = QLineEdit(initial_color.name())
        self.color_edit.setPlaceholderText("#RRGGBB")
        self.color_edit.setMaximumWidth(120)
        self._update_color_swatch(initial_color)
        self.color_pick_btn = QPushButton("Pick…")
        self.color_pick_btn.clicked.connect(self._pick_color)
        color_row.addWidget(self.color_edit)
        color_row.addWidget(self.color_pick_btn)
        color_row.addStretch()
        form.addRow("Curve color:", color_row)

        # ---- Background ----
        bg_row = QHBoxLayout()
        self.bg_edit = QLineEdit(settings.get("background_path") or "")
        self.bg_edit.setPlaceholderText("(no background)")
        self.bg_edit.setReadOnly(True)
        bg_browse = QPushButton("Browse…")
        bg_browse.clicked.connect(self._browse_background)
        bg_clear = QPushButton("Clear")
        bg_clear.clicked.connect(lambda: self.bg_edit.setText(""))
        bg_row.addWidget(self.bg_edit, 1)
        bg_row.addWidget(bg_browse)
        bg_row.addWidget(bg_clear)
        form.addRow("Background:", bg_row)

        # ---- JSON save directory ----
        json_row = QHBoxLayout()
        self.json_edit = QLineEdit(settings.get("json_dir") or "")
        self.json_edit.setPlaceholderText("(system default)")
        json_browse = QPushButton("Browse…")
        json_browse.clicked.connect(lambda: self._browse_dir(self.json_edit))
        json_row.addWidget(self.json_edit, 1)
        json_row.addWidget(json_browse)
        form.addRow("JSON save dir:", json_row)

        # ---- SVG save directory ----
        svg_row = QHBoxLayout()
        self.svg_edit = QLineEdit(settings.get("svg_dir") or "")
        self.svg_edit.setPlaceholderText("(system default)")
        svg_browse = QPushButton("Browse…")
        svg_browse.clicked.connect(lambda: self._browse_dir(self.svg_edit))
        svg_row.addWidget(self.svg_edit, 1)
        svg_row.addWidget(svg_browse)
        form.addRow("SVG save dir:", svg_row)

        layout.addLayout(form)

        # ---- Buttons ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------
    #  Helpers
    # ------------------------------------------------------------
    def _update_color_swatch(self, color: QColor):
        if color.isValid():
            self.color_edit.setStyleSheet(
                f"background-color: {color.name()}; "
                f"color: {'white' if color.lightness() < 128 else 'black'};"
            )

    def _pick_color(self):
        current = QColor(self.color_edit.text())
        if not current.isValid():
            current = QColor(90, 90, 90)
        color = QColorDialog.getColor(current, self, "Curve Color")
        if color.isValid():
            self.color_edit.setText(color.name())
            self._update_color_swatch(color)

    def _browse_background(self):
        start = self.bg_edit.text() or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", start,
            "Images (*.png *.jpg *.jpeg *.svg);;All files (*)")
        if path:
            self.bg_edit.setText(path)

    def _browse_dir(self, line_edit: QLineEdit):
        start = line_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", start)
        if folder:
            line_edit.setText(folder)

    def _validate_and_accept(self):
        # Validate curve color
        color_text = self.color_edit.text().strip()
        color = QColor(color_text)
        if not color.isValid():
            self.color_edit.setStyleSheet("background-color: #ffcccc;")
            return  # refuse to accept
        self.accept()

    # ------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------
    def values(self) -> dict:
        return {
            "canvas_width": self.canvas_w.value(),
            "canvas_height": self.canvas_h.value(),
            "stroke_width": self.stroke_spin.value(),
            "curve_color": self.color_edit.text().strip(),
            "background_path": self.bg_edit.text().strip() or None,
            "json_dir": self.json_edit.text().strip(),
            "svg_dir": self.svg_edit.text().strip(),
        }