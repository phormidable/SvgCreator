from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,QDialogButtonBox


class FilePathsDialog(QDialog):
    """Dialog to configure default save directories for JSON and SVG files."""

    def __init__(self, json_path: str, svg_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Paths")
        self.setModal(True)
        self.resize(500, 150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # ---- JSON path row ----
        json_row = QHBoxLayout()
        json_label = QLabel("JSON save directory:")
        json_label.setMinimumWidth(150)
        self.json_edit = QLineEdit(json_path)
        self.json_edit.setPlaceholderText("/path/to/json/folder")
        json_browse = QPushButton("Browse…")
        json_browse.clicked.connect(lambda: self._browse(self.json_edit))
        json_row.addWidget(json_label)
        json_row.addWidget(self.json_edit, 1)
        json_row.addWidget(json_browse)
        layout.addLayout(json_row)

        # ---- SVG path row ----
        svg_row = QHBoxLayout()
        svg_label = QLabel("SVG save directory:")
        svg_label.setMinimumWidth(150)
        self.svg_edit = QLineEdit(svg_path)
        self.svg_edit.setPlaceholderText("/path/to/svg/folder")
        svg_browse = QPushButton("Browse…")
        svg_browse.clicked.connect(lambda: self._browse(self.svg_edit))
        svg_row.addWidget(svg_label)
        svg_row.addWidget(self.svg_edit, 1)
        svg_row.addWidget(svg_browse)
        layout.addLayout(svg_row)

        # ---- Buttons ----
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self, line_edit: QLineEdit):
        start_dir = line_edit.text() or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", start_dir)
        if folder:
            line_edit.setText(folder)

    def values(self) -> tuple[str, str]:
        return self.json_edit.text().strip(), self.svg_edit.text().strip()