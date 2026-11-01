from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QSpinBox, QDialogButtonBox)


class StrokeWidthDialog(QDialog):
    """Dialog to set the default stroke width for new stroke curves."""

    def __init__(self, current_width: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stroke Width")
        self.setModal(True)
        self.resize(300, 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        row = QHBoxLayout()
        label = QLabel("Stroke width (scene units):")
        self.spin = QSpinBox()
        self.spin.setRange(1, 5000)
        self.spin.setValue(current_width)
        self.spin.setSingleStep(10)
        row.addWidget(label)
        row.addWidget(self.spin, 1)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> int:
        return self.spin.value()