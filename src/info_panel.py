# info_panel.py
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QPlainTextEdit)
from PySide6.QtCore import Qt


class InfoPanel(QGroupBox):
    """Right-hand panel: curve selector, point coordinates, event console."""

    def __init__(self, scene, parent=None):
        super().__init__("Selected Curve Points", parent)
        self.scene = scene
        self.updating_combobox = False
        #self.point_fields = [None] * 4   # indexed by point_idx
        self.point_fields: dict[int, tuple[QLineEdit, QLineEdit]] = {}
        outer = QVBoxLayout()
        outer.setSpacing(6)

        # ---- Two columns ----
        columns = QHBoxLayout()
        columns.setSpacing(24)

        def make_field_row(label_text, point_idx):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(50)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)

            x_field = QLineEdit()
            y_field = QLineEdit()
            for f in (x_field, y_field):
                f.setReadOnly(True)
                f.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                f.setMaximumWidth(80)
            row.addWidget(x_field)
            row.addWidget(y_field)
            row.addStretch()

            self.point_fields[point_idx] = (x_field, y_field)
            return row

        # --- Left column: Curve + Start + End ---
        left = QVBoxLayout()
        left.setSpacing(2)

        curve_row = QHBoxLayout()
        curve_label = QLabel("Curve:")
        curve_label.setFixedWidth(50)
        curve_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.curve_combo = QComboBox()
        self.curve_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.curve_combo.currentIndexChanged.connect(self.on_curve_selected)
        curve_row.addWidget(curve_label)
        curve_row.addWidget(self.curve_combo, 1)
        left.addLayout(curve_row)
        left.addLayout(make_field_row("Start:", 0))
        left.addLayout(make_field_row("End:", 3))
        left.addStretch()

        # --- Right column: P1 + P2 ---
        right = QVBoxLayout()
        right.setSpacing(2)
        right.addLayout(make_field_row("P1:", 1))
        right.addLayout(make_field_row("P2:", 2))
        right.addStretch()

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        outer.addLayout(columns)

        # ---- Console ----
        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.console.setMaximumBlockCount(500)
        self.console.setPlaceholderText("Events will appear here…")
        self.console.setFixedHeight(120)
        outer.addWidget(self.console)

        self.setLayout(outer)

        # ---- Wire to scene ----
        scene.pointsChanged.connect(self.update_info_panel)
        scene.curveListChanged.connect(self.update_curve_combobox)
        scene.curveSelected.connect(self.on_scene_curve_selected)
        scene.curveDragFinished.connect(self.update_info_panel)
        scene.messageLogged.connect(self.log)

        # Initial population (combobox first; it calls update_info_panel).
        self.update_curve_combobox()

    # ---- Slots ----
    def log(self, message: str):
        self.console.appendPlainText(message)

    def on_curve_selected(self, index):
        if self.updating_combobox:
            return
        self.scene.selected_curve_idx = index
        self.update_info_panel()

    def on_scene_curve_selected(self, index):
        # Setting the combo index fires currentIndexChanged → on_curve_selected,
        # which updates the info panel.
        self.curve_combo.setCurrentIndex(index)

    def update_info_panel(self):
        curve_idx = self.curve_combo.currentIndex()
        points = self.scene.get_curve_points(curve_idx)
        if points:
            for i, pt in enumerate(points):
                pos = pt.pos()
                x_field, y_field = self.point_fields[i]
                x_field.setText(f"{pos.x():.2f}")
                y_field.setText(f"{pos.y():.2f}")
        else:
            for x_field, y_field in self.point_fields.values():
                x_field.setText("")
                y_field.setText("")

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
        self.update_info_panel()