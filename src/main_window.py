# main_window.py
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit,
    QFileDialog, QMessageBox, QLabel, QDoubleSpinBox,
    QGroupBox, QGridLayout, QComboBox
)
from PySide6.QtCore import QByteArray, Qt, QPointF
from PySide6.QtGui import QPainter, QFont, QActionGroup
from PySide6.QtSvgWidgets import QSvgWidget

from settings import (
    CANVAS_WIDTH, CANVAS_HEIGHT,
    PREVIEW_WIDTH, PREVIEW_HEIGHT,
    INFO_HEIGHT, CODE_EDIT_HEIGHT,
)
from bezier_scene import BezierScene
from custom_view import CustomGraphicsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bézier SVG Creator")
        self.resize(CANVAS_WIDTH + PREVIEW_WIDTH,
                    CANVAS_HEIGHT + INFO_HEIGHT + CODE_EDIT_HEIGHT + 50)

        self.updating_spinboxes = False
        self.updating_combobox = False

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- Top row ----
        top_row = QHBoxLayout()
        top_row.setSpacing(5)

        self.drawing_view = CustomGraphicsView()
        self.drawing_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.drawing_view.setFixedSize(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.scene = BezierScene()
        self.drawing_view.setScene(self.scene)
        top_row.addWidget(self.drawing_view)

        self.preview_widget = QSvgWidget()
        self.preview_widget.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_widget.setStyleSheet("background-color: white;")
        top_row.addWidget(self.preview_widget)

        main_layout.addLayout(top_row)

        # ---- Bottom area ----
        bottom_split = QVBoxLayout()
        bottom_split.setSpacing(2)

        # Info zone
        self.info_widget = self.create_info_panel()
        self.info_widget.setFixedHeight(INFO_HEIGHT)
        bottom_split.addWidget(self.info_widget)

        # Code zone
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFixedHeight(CODE_EDIT_HEIGHT)
        self.code_edit.setFont(QFont("Courier New", 10))
        self.code_edit.setReadOnly(True)
        bottom_split.addWidget(self.code_edit)

        main_layout.addLayout(bottom_split)

        # ---- Toolbar ----
        self.setup_toolbar()

        # ---- Mouse coordinate label ----
        self.coord_label = QLabel(self.drawing_view)
        self.coord_label.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; "
            "padding: 2px 5px; border-radius: 3px; font-weight: bold;"
        )
        self.coord_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.coord_label.hide()

        # ---- Connect signals ----
        self.scene.svgCodeChanged.connect(self.update_preview_and_code)
        self.scene.pointsChanged.connect(self.update_info_panel)
        self.scene.curveListChanged.connect(self.update_curve_combobox)
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()
        self.update_info_panel()
        self.update_curve_combobox()

    # ------------------------------------------------------------
    #  Info panel with combobox and spinboxes
    # ------------------------------------------------------------
    def create_info_panel(self):
        group = QGroupBox("Selected Curve Points")
        layout = QGridLayout()
        layout.setVerticalSpacing(2)
        layout.setHorizontalSpacing(10)

        # Combobox row
        self.curve_combo = QComboBox()
        self.curve_combo.currentIndexChanged.connect(self.on_curve_selected)
        layout.addWidget(QLabel("Curve:"), 0, 0)
        layout.addWidget(self.curve_combo, 0, 1, 1, 2)

        # Spinboxes for 4 points
        self.point_spinboxes = []
        point_labels = ["P0 (start)", "P1 (control)", "P2 (control)", "P3 (end)"]

        for i, label in enumerate(point_labels):
            row = i + 1
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(lbl, row, 0)

            x_spin = QDoubleSpinBox()
            x_spin.setRange(-9999, 9999)
            x_spin.setDecimals(2)
            x_spin.setSingleStep(1.0)
            x_spin.setProperty("point_idx", i)
            layout.addWidget(x_spin, row, 1)

            y_spin = QDoubleSpinBox()
            y_spin.setRange(-9999, 9999)
            y_spin.setDecimals(2)
            y_spin.setSingleStep(1.0)
            y_spin.setProperty("point_idx", i)
            layout.addWidget(y_spin, row, 2)

            self.point_spinboxes.append((x_spin, y_spin))

        group.setLayout(layout)
        return group

    def connect_spinboxes(self):
        for i, (x_spin, y_spin) in enumerate(self.point_spinboxes):
            x_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx, is_x=True))
            y_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx, is_x=False))

    def on_spinbox_changed(self, point_idx, is_x):
        if self.updating_spinboxes:
            return
        curve_idx = self.curve_combo.currentIndex()
        if curve_idx < 0:
            return
        x_spin, y_spin = self.point_spinboxes[point_idx]
        new_pos = QPointF(x_spin.value(), y_spin.value())
        self.scene.move_selected_point(curve_idx, point_idx, new_pos)

    def on_curve_selected(self, index):
        if self.updating_combobox:
            return
        self.update_info_panel()

    def update_info_panel(self):
        """Populate spinboxes from the currently selected curve."""
        if self.updating_spinboxes:
            return
        self.updating_spinboxes = True

        curve_idx = self.curve_combo.currentIndex()
        points = self.scene.get_curve_points(curve_idx)
        if points:
            for i, pt in enumerate(points):
                pos = pt.pos()
                x_spin, y_spin = self.point_spinboxes[i]
                x_spin.blockSignals(True)
                y_spin.blockSignals(True)
                x_spin.setValue(pos.x())
                y_spin.setValue(pos.y())
                x_spin.blockSignals(False)
                y_spin.blockSignals(False)
        else:
            for x_spin, y_spin in self.point_spinboxes:
                x_spin.blockSignals(True)
                y_spin.blockSignals(True)
                x_spin.setValue(0.0)
                y_spin.setValue(0.0)
                x_spin.blockSignals(False)
                y_spin.blockSignals(False)

        self.updating_spinboxes = False

    def update_curve_combobox(self):
        """Update the combobox with current curve list."""
        if self.updating_combobox:
            return
        self.updating_combobox = True
        self.curve_combo.blockSignals(True)
        self.curve_combo.clear()
        for i in range(len(self.scene.curves)):
            self.curve_combo.addItem(f"Curve {i+1}")
        if self.scene.curves:
            # Select the last one (or the one that was selected before)
            idx = self.scene.selected_curve_idx
            if idx < 0 or idx >= len(self.scene.curves):
                idx = len(self.scene.curves) - 1
            self.curve_combo.setCurrentIndex(idx)
        else:
            # No curves, clear spinboxes
            self.update_info_panel()
        self.curve_combo.blockSignals(False)
        self.updating_combobox = False

    # ------------------------------------------------------------
    #  Mouse coordinate label
    # ------------------------------------------------------------
    def show_mouse_coordinates(self, scene_pos: QPointF):
        text = f"({scene_pos.x():.1f}, {scene_pos.y():.1f})"
        self.coord_label.setText(text)
        self.coord_label.adjustSize()

        cursor_pos = self.drawing_view.mapFromGlobal(self.drawing_view.cursor().pos())
        x = cursor_pos.x() + 15
        y = cursor_pos.y() - 5
        max_x = self.drawing_view.width() - self.coord_label.width()
        max_y = self.drawing_view.height() - self.coord_label.height()
        x = min(max(x, 0), max_x)
        y = min(max(y, 0), max_y)
        self.coord_label.move(x, y)
        self.coord_label.show()

    # ------------------------------------------------------------
    #  Toolbar
    # ------------------------------------------------------------
    def setup_toolbar(self):
        toolbar = self.addToolBar("Tools")

        self.create_action = toolbar.addAction("✏️ Create")
        self.create_action.setCheckable(True)
        self.edit_action = toolbar.addAction("🖱️ Edit")
        self.edit_action.setCheckable(True)

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addAction(self.create_action)
        self.mode_group.addAction(self.edit_action)
        self.create_action.setChecked(True)

        self.create_action.triggered.connect(lambda: self.set_mode("create"))
        self.edit_action.triggered.connect(lambda: self.set_mode("edit"))

        toolbar.addSeparator()

        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

        export_action = toolbar.addAction("💾 Export SVG")
        export_action.triggered.connect(self.export_svg)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        self.scene.mode = mode
        self.drawing_view.set_mode(mode)
        if mode == "create":
            self.statusBar().showMessage("Create mode: click to place points. Drag background to pan.")
        else:
            self.statusBar().showMessage("Edit mode: drag points or edit coordinates. Drag empty space to pan.")

    # ------------------------------------------------------------
    #  Update preview & code
    # ------------------------------------------------------------
    def update_preview_and_code(self, svg_string):
        self.preview_widget.load(QByteArray(svg_string.encode()))
        self.code_edit.setPlainText(svg_string)

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()
        self.update_info_panel()
        self.update_curve_combobox()

    # ------------------------------------------------------------
    #  Export
    # ------------------------------------------------------------
    def export_svg(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save SVG", "", "SVG files (*.svg)"
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self.scene.generate_svg())
                self.statusBar().showMessage(f"✅ Exported to {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")