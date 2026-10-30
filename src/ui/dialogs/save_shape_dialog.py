# ui/dialogs/save_shape_dialog.py
"""Dialog for the Save Shape action: name, tooltip, and a read-only
description of what is being saved."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                               QLineEdit, QPlainTextEdit, QVBoxLayout)


class SaveShapeDialog(QDialog):
    def __init__(self, description: str, default_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Shape")
        self.resize(480, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form = QFormLayout()
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setPlaceholderText("e.g. Star")
        form.addRow("Name:", self.name_edit)

        self.tooltip_edit = QLineEdit()
        self.tooltip_edit.setPlaceholderText(
            "Optional. Shown as a tooltip in the preset panel.")
        form.addRow("Tooltip:", self.tooltip_edit)
        layout.addLayout(form)

        self.description = QPlainTextEdit(description)
        self.description.setReadOnly(True)
        self.description.setFont(QFont("Courier New", 9))
        layout.addWidget(self.description, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def _on_accept(self):
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            return
        self.accept()

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.tooltip_edit.text().strip()