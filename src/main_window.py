# main_window.py
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGraphicsView, QPlainTextEdit,
    QFileDialog, QMessageBox, QLabel, QDoubleSpinBox,
    QGroupBox, QGridLayout
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

        self.updating_spinboxes = False  # flag to avoid feedback loops

        # Central widget and main layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- Top row: Canvas + Preview ----
        top_row = QHBoxLayout()
        top_row.setSpacing(5)

        # Zone 1: Drawing canvas (custom view)
        self.drawing_view = CustomGraphicsView()
        self.drawing_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.drawing_view.setFixedSize(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.scene = BezierScene()
        self.drawing_view.setScene(self.scene)
        top_row.addWidget(self.drawing_view)

        # Zone 3: SVG preview
        self.preview_widget = QSvgWidget()
        self.preview_widget.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_widget.setStyleSheet("background-color: white;")
        top_row.addWidget(self.preview_widget)

        main_layout.addLayout(top_row)

        # ---- Bottom area: Info zone (top) + Code zone (bottom) ----
        bottom_split = QVBoxLayout()
        bottom_split.setSpacing(2)

        # Info zone (editable coordinates for selected curve)
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

        # ---- Mouse coordinate label (floating) ----
        self.coord_label = QLabel(self.drawing_view)
        self.coord_label.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; "
            "padding: 2px 5px; border-radius: 3px; font-weight: bold;"
        )
        self.coord_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.coord_label.hide()

        # Connect signals
        self.scene.svgCodeChanged.connect(self.update_preview_and_code)
        self.scene.pointsChanged.connect(self.update_info_panel)
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()
        self.update_info_panel()

    # ------------------------------------------------------------
    #  Info panel with spinboxes
    # ------------------------------------------------------------
    def create_info_panel(self):
        group = QGroupBox("Selected Curve Points")
        layout = QGridLayout()
        layout.setVerticalSpacing(2)
        layout.setHorizontalSpacing(10)

        # Store spinboxes in a list of tuples (x_spin, y_spin)
        self.point_spinboxes = []
        point_labels = ["P0 (start)", "P1 (control)", "P2 (control)", "P3 (end)"]

        for i, label in enumerate(point_labels):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(lbl, i, 0)

            x_spin = QDoubleSpinBox()
            x_spin.setRange(-9999, 9999)
            x_spin.setDecimals(2)
            x_spin.setSingleStep(1.0)
            x_spin.setProperty("point_idx", i)   # store point index
            layout.addWidget(x_spin, i, 1)

            y_spin = QDoubleSpinBox()
            y_spin.setRange(-9999, 9999)
            y_spin.setDecimals(2)
            y_spin.setSingleStep(1.0)
            y_spin.setProperty("point_idx", i)
            layout.addWidget(y_spin, i, 2)

            # Connect signals (will be connected later after we have the scene)
            self.point_spinboxes.append((x_spin, y_spin))

        group.setLayout(layout)
        return group

    def connect_spinboxes(self):
        """Connect spinbox valueChanged signals to the update method."""
        for i, (x_spin, y_spin) in enumerate(self.point_spinboxes):
            x_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx, is_x=True))
            y_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx, is_x=False))

    def on_spinbox_changed(self, point_idx, is_x):
        if self.updating_spinboxes:
            return
        x_spin, y_spin = self.point_spinboxes[point_idx]
        new_pos = QPointF(x_spin.value(), y_spin.value())
        self.scene.move_selected_point(point_idx, new_pos)

    def update_info_panel(self):
        """Populate spinboxes from the selected curve."""
        if self.updating_spinboxes:
            return
        self.updating_spinboxes = True

        curve = self.scene.get_selected_curve()
        if curve and len(curve) == 4:
            for i, pt in enumerate(curve):
                pos = pt.pos()
                x_spin, y_spin = self.point_spinboxes[i]
                # Block signals to avoid feedback
                x_spin.blockSignals(True)
                y_spin.blockSignals(True)
                x_spin.setValue(pos.x())
                y_spin.setValue(pos.y())
                x_spin.blockSignals(False)
                y_spin.blockSignals(False)
        else:
            # No curve selected → clear spinboxes
            for x_spin, y_spin in self.point_spinboxes:
                x_spin.blockSignals(True)
                y_spin.blockSignals(True)
                x_spin.setValue(0.0)
                y_spin.setValue(0.0)
                x_spin.blockSignals(False)
                y_spin.blockSignals(False)

        self.updating_spinboxes = False

    # ------------------------------------------------------------
    #  Mouse coordinate label
    # ------------------------------------------------------------
    def show_mouse_coordinates(self, scene_pos: QPointF):
        # Update the label text and position
        text = f"({scene_pos.x():.1f}, {scene_pos.y():.1f})"
        self.coord_label.setText(text)
        self.coord_label.adjustSize()

        # Get cursor position relative to the view
        cursor_pos = self.drawing_view.mapFromGlobal(self.drawing_view.cursor().pos())
        # Offset to place bottom‑right of cursor
        x = cursor_pos.x() + 15
        y = cursor_pos.y() - 5
        # Ensure label stays inside the view
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
        if mode == "create":
            self.drawing_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.statusBar().showMessage("Create mode: click to place points. Drag background to pan.")
        else:
            self.drawing_view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.statusBar().showMessage("Edit mode: drag points or edit coordinates in the info panel.")

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