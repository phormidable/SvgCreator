# main_window.py
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,QPlainTextEdit, QApplication,
    QFileDialog, QMessageBox, QLabel, QDoubleSpinBox,QGroupBox, QGridLayout, QComboBox, QDialog, QDialogButtonBox)
from PySide6.QtCore import QByteArray, Qt, QPointF
from PySide6.QtGui import QPainter, QFont, QActionGroup
from PySide6.QtSvgWidgets import QSvgWidget

from settings import CANVAS_WIDTH, CANVAS_HEIGHT,PREVIEW_WIDTH, PREVIEW_HEIGHT,INFO_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT
from bezier_scene import BezierScene
from custom_view import CustomGraphicsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bézier SVG Creator")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

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
        self.info_widget = self._create_info_panel()
        self.info_widget.setFixedHeight(INFO_HEIGHT)
        self.connect_spinboxes()
        main_layout.addWidget(self.info_widget)

        # ---- Toolbar ----
        self._setup_toolbar()

        # ---- Mouse coordinate label ----
        self.coord_label = QLabel(self.drawing_view.viewport())
        self.coord_label.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; "
            "padding: 2px 5px; border-radius: 3px; font-weight: bold;"
        )
        self.coord_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.coord_label.setText("(0.0, 0.0)")  # initial text
        self.coord_label.adjustSize()
        self.coord_label.move(10, 10)  # initial position
        self.coord_label.show()  # show from the start
        self.coord_label.raise_()  # ensure it's on top

        # ---- Connect signals ----
        self.scene.svgCodeChanged.connect(self.update_preview)
        self.scene.pointsChanged.connect(self.update_info_panel)
        self.scene.curveListChanged.connect(self.update_curve_combobox)
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)
        self.drawing_view.mouseMoved.connect(self.scene.on_mouse_moved)
        self.scene.curveSelected.connect(self.on_scene_curve_selected)
        self.scene.curveDragFinished.connect(self.update_info_panel)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()
        self.update_info_panel()
        self.update_curve_combobox()

    # ------------------------------------------------------------
    #  Info panel with combobox and spinboxes
    # ------------------------------------------------------------
    def _create_info_panel(self):
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
            x_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx))
            y_spin.valueChanged.connect(lambda val, idx=i: self.on_spinbox_changed(idx))

    def on_spinbox_changed(self, point_idx):
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
        self.scene.selected_curve_idx = index
        self.update_info_panel()

    def on_scene_curve_selected(self, index):
        # Setting the combo index fires currentIndexChanged → on_curve_selected,
        # which updates the info panel. No need to call it manually here.
        self.curve_combo.setCurrentIndex(index)

    def update_info_panel(self):
        """Populate spinboxes from the currently selected curve."""
        if self.updating_spinboxes:
            return
        if self.scene.dragging_curve is not None:
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
            self.curve_combo.addItem(self.scene.curves[i].name)
        if self.scene.curves:
            # Select the last one (or the one that was selected before)
            idx = self.scene.selected_curve_idx
            if idx < 0 or idx >= len(self.scene.curves):
                idx = len(self.scene.curves) - 1
            self.curve_combo.setCurrentIndex(idx)
        self.curve_combo.blockSignals(False)
        self.updating_combobox = False
        self.update_info_panel()

    # ------------------------------------------------------------
    #  Mouse coordinate label
    # ------------------------------------------------------------
    def show_mouse_coordinates(self, scene_pos):
        if scene_pos is None:
            self.coord_label.hide()
            return

        text = f"({scene_pos.x():.1f}, {scene_pos.y():.1f})"
        self.coord_label.setText(text)
        self.coord_label.adjustSize()

        vp = self.drawing_view.mapFromScene(scene_pos)
        x = vp.x() + 15
        y = vp.y() + 15
        max_x = self.drawing_view.width() - self.coord_label.width()
        max_y = self.drawing_view.height() - self.coord_label.height()
        x = min(max(x, 0), max_x)
        y = min(max(y, 0), max_y)
        self.coord_label.move(x, y)
        self.coord_label.show()
        self.coord_label.raise_()

    # ------------------------------------------------------------
    #  Toolbar
    # ------------------------------------------------------------
    def _setup_toolbar(self):
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

        # Zoom
        self.zoom_group = QActionGroup(self)
        self.zoom_group.setExclusive(True)
        self.zoom_actions = {}

        zoom_levels = [
            ("1x", 1.0, "Ctrl+1"),
            ("2x", 2.0, "Ctrl+2"),
            ("4x", 4.0, "Ctrl+3"),
            ("8x", 8.0, "Ctrl+4"),
            ("16x", 16.0, "Ctrl+5"),
        ]
        for label, factor, shortcut in zoom_levels:
            action = toolbar.addAction(label)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setToolTip(f"Zoom {label}  ({shortcut})")
            action.triggered.connect(lambda checked=False, f=factor: self.drawing_view.set_zoom(f))
            self.zoom_group.addAction(action)
            self.zoom_actions[factor] = action
        self.zoom_actions[1.0].setChecked(True)

        toolbar.addSeparator()

        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

        generate_action = toolbar.addAction("📄 Generate SVG code")
        generate_action.triggered.connect(self.show_svg_code_dialog)

        export_action = toolbar.addAction("💾 Export SVG")
        export_action.triggered.connect(self.export_svg)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        # If switching to Edit and there are incomplete points, discard them
        if mode == "edit" and self.scene.pending_curve is not None:
            self.scene.discard_current_points()
            self.statusBar().showMessage("Incomplete curve discarded. Switch to Edit mode.")

        self.scene.mode = mode
        if mode == "create":
            self.statusBar().showMessage("Create mode: left-click to place points. Right-drag to pan.")
        else:
            self.statusBar().showMessage("Edit mode: drag points or edit coordinates. Right-drag to pan.")

        self.coord_label.show()

    # ------------------------------------------------------------
    #  Update preview & code
    # ------------------------------------------------------------
    def update_preview(self, svg_string):
        self.preview_widget.load(QByteArray(svg_string.encode()))

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()

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

    # ------------------------------------------------------------
    #  Show svg code
    # ------------------------------------------------------------
    def show_svg_code_dialog(self):
        svg_string = self.scene.generate_svg()

        dialog = QDialog(self)
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
        copy_btn = buttons.addButton("Copy to clipboard", QDialogButtonBox.ButtonRole.ActionRole)
        close_btn = buttons.addButton(QDialogButtonBox.StandardButton.Close)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(svg_string))
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()