# ui/dialogs/canvas_size_dialog.py
"""CanvasSizeDialog: set the viewbox width and height.

The viewbox stays centered on the origin — the dialog only exposes the
two dimensions. Range is bounded by settings.CANVAS_MIN_SIZE / MAX_SIZE,
which the app applies everywhere a size can enter (dialog, load_state
warning). The artboard stays fixed at ARTBOARD_RECT.
"""

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QSpinBox, QVBoxLayout)

from core.settings import CANVAS_MIN_SIZE, CANVAS_MAX_SIZE


class CanvasSizeDialog(QDialog):
    def __init__(self, width: float, height: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Canvas Size")
        self.resize(320, 170)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.width_spin = QSpinBox()
        self.width_spin.setRange(CANVAS_MIN_SIZE, CANVAS_MAX_SIZE)
        self.width_spin.setValue(int(round(width)))
        self.width_spin.setSuffix(" px")
        form.addRow("Width:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(CANVAS_MIN_SIZE, CANVAS_MAX_SIZE)
        self.height_spin.setValue(int(round(height)))
        self.height_spin.setSuffix(" px")
        form.addRow("Height:", self.height_spin)

        layout.addLayout(form)

        info = QLabel(
            "The viewbox is centered on the origin.\n"
            f"Allowed range: {CANVAS_MIN_SIZE}–{CANVAS_MAX_SIZE} px.")
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, int]:
        return self.width_spin.value(), self.height_spin.value()