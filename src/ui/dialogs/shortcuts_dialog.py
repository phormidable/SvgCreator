# ui/dialogs/shortcuts_dialog.py
"""Shortcuts dialog: a table of key → action, grouped by section.

The list below is hand-maintained. It duplicates the truth that lives in
MainWindow._build_key_handlers, the Tab QShortcut, and the toolbar action
shortcuts — keep it in sync when adding a binding.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHeaderView,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)


# (key, action): action=None marks a section header row.
SHORTCUTS = [
    ("Mode & creation", None),
    ("Tab",             "Toggle Create / Edit mode"),
    ("Left-click",      "Place a point (Create mode)"),
    ("Escape",          "Discard the in-progress curve"),

    ("Selection", None),
    ("Ctrl + A",        "Select all points  (again to deselect)"),
    ("Ctrl + C",        "Copy the current selection"),
    ("Ctrl + V",        "Paste the copied content at the cursor"),
    ("Click",           "Select a point"),
    ("Shift + Click",   "Toggle a point in the selection"),
    ("A",               "Select curve under cursor  (Shift+A adds)"),
    ("S",               "Select shape under cursor  (Shift+S adds)"),
    ("Escape",          "Clear selection"),

    ("Editing", None),
    ("Ctrl + Z",         "Undo the last action"),
    ("Ctrl + Y / Ctrl+Shift+Z", "Redo the last undone action"),
    ("Arrow keys",      "Nudge selected points by 1 unit"),
    ("Backspace",       "Delete selection"),
    ("H",               "Hide points on the hovered curve"),
    ("U",               "Break the junction under the cursor"),


    ("Transform", None),
    ("R",               "Rotate the selection"),
    ("B",               "Scale the selection"),
    ("M",               "Move the selection (follows the mouse)"),
    ("Left-click",      "Validate the transform"),
    ("Escape",          "Cancel the transform"),

    ("Linking", None),
    ("L",               "Link the dragged point to the flashing target"),
    ("J", "Connect 2 selected points with a line"),
    ("Ctrl + J", "Connect and link the 2 selected points"),

    ("Appearance", None),
    ("C",               "Pick a colour for the selected shape"),
    ("X",               "Mirror across the horizontal axis"),
    ("Y",               "Mirror across the vertical axis"),

    ("View", None),
    ("Right-drag",      "Pan the drawing view"),
    ("+  /  =",         "Zoom in"),
    ("-",               "Zoom out"),

    ("File", None),
    ("Ctrl + O",        "Load a project"),
    ("Ctrl + S",        "Save the project"),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(480, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self._build_table())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        layout.addWidget(buttons)

    @staticmethod
    def _build_table() -> QTableWidget:
        table = QTableWidget(len(SHORTCUTS), 2)
        table.setHorizontalHeaderLabels(["Key", "Action"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(False)

        bold = QFont()
        bold.setBold(True)

        for r, (key, action) in enumerate(SHORTCUTS):
            if action is None:
                item = QTableWidgetItem(key)
                item.setFont(bold)
                table.setItem(r, 0, item)
                table.setSpan(r, 0, 1, 2)
                table.setRowHeight(r, 30)
            else:
                table.setItem(r, 0, QTableWidgetItem(key))
                table.setItem(r, 1, QTableWidgetItem(action))
                table.setRowHeight(r, 22)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        return table