# main_window.py
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QColorDialog, QComboBox, QSizePolicy
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QActionGroup, QColor, QShortcut, QKeySequence

from settings import DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT
from bezier_scene import BezierScene
from custom_view import CustomGraphicsView
from info_panel import InfoPanel
from file_io import FileIO
from preview_widget import PreviewWidget
from preset_panel import PresetPanel

ZOOM_LEVELS = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0),
               ("4x", 4.0), ("8x", 8.0), ("16x", 16.0)]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bézier SVG Creator")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout: [ drawing ] | [ preview / info ]
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- Left column: drawing view (the main zone) ----
        self.drawing_view = CustomGraphicsView()
        self.drawing_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.drawing_view.setMinimumSize(DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT)
        # no setFixedSize — let the layout stretch it
        self.scene = BezierScene()
        self.drawing_view.setScene(self.scene)
        main_layout.addWidget(self.drawing_view, 1)  # stretch = 1, take all the room
        self.file_io = FileIO(self)

        # ---- Right column: preview on top, info below ----
        right_col = QVBoxLayout()
        right_col.setSpacing(5)

        self.preview_widget = PreviewWidget()
        self.preview_widget.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        right_col.addWidget(self.preview_widget)

        self.preset_panel = PresetPanel()
        right_col.addWidget(self.preset_panel)

        self.info_panel = InfoPanel(self.scene)
        right_col.addWidget(self.info_panel, 1)
        main_layout.addLayout(right_col)
        # ---- Toolbar ----
        self._setup_toolbar()

        # Why a shortcut and not a keyPressEvent branch: Qt intercepts Tab for focus
        # traversal in QWidget::event() before keyPressEvent, so the drawing view would
        # swallow it. A window-level QShortcut is dispatched earlier, so it always fires.
        self._tab_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Tab), self)
        self._tab_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._tab_shortcut.activated.connect(self._toggle_mode)

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
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)
        self.drawing_view.mouseMoved.connect(self.scene.on_mouse_moved)
        self.scene.transformModeChanged.connect(self.drawing_view.set_transform_mode)
        self.drawing_view.transformLeftClick.connect(self.scene.end_transform)
        self.preset_panel.presetRequested.connect(self.scene.arm_preset)
        self.scene.presetStateChanged.connect(self.preset_panel.sync_state)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()

    def _toggle_mode(self):
        new_mode = "edit" if self.scene.mode == "create" else "create"
        self.set_mode(new_mode)

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            if self.scene.is_rotating():
                self.scene.end_transform(commit=False)
                event.accept()
                return
            if self.scene.cancel_preset():
                event.accept()
                return
            self.scene.clear_selection()
            if self.scene.cancel_pending_curve():
                event.accept()
                return
        elif key == Qt.Key.Key_R:
            if self.scene.start_rotation():
                event.accept()
                return
        elif key == Qt.Key.Key_B:
            if self.scene.start_scaling():
                event.accept()
                return
        elif key == Qt.Key.Key_L:
            if self.scene.link_manager.try_link_proximity():
                event.accept()
                return
        elif key == Qt.Key.Key_S:
            add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self.scene.shape_manager.select_from_hover(add=add):
                event.accept()
                return
        elif key == Qt.Key.Key_C:
            self.color_selected_shape()
            event.accept()
            return
        elif key == Qt.Key.Key_H:
            if self.scene.hide_hovered_curve_points():
                event.accept()
                return
        elif key == Qt.Key.Key_A:
            add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self.scene.select_curve_under_hover(add=add):
                event.accept()
                return
        elif key == Qt.Key.Key_X:
            if self.scene.mirror_selection("x"):
                event.accept()
                return
        elif key == Qt.Key.Key_Y:
            if self.scene.mirror_selection("y"):
                event.accept()
                return
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._step_zoom(+1)
            event.accept()
            return
        elif key == Qt.Key.Key_Minus:
            self._step_zoom(-1)
            event.accept()
            return
        elif key == Qt.Key.Key_D:
            self._debug_sizes()
            event.accept()
            return
        elif key == Qt.Key.Key_Backspace:
            if self.scene.delete_selection():
                event.accept()
                return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            dx = -1 if key == Qt.Key.Key_Left else 1 if key == Qt.Key.Key_Right else 0
            dy = -1 if key == Qt.Key.Key_Up else 1 if key == Qt.Key.Key_Down else 0
            if self.scene.move_selected_points(dx, dy):
                event.accept()
                return

        super().keyPressEvent(event)

    def log(self, message: str):
        self.info_panel.log(message)

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

        # ---- Mode ----
        self.create_action = toolbar.addAction("✏️ Create")
        self.create_action.setCheckable(True)
        self.edit_action = toolbar.addAction("🖱️ Edit")
        self.edit_action.setCheckable(True)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Type: "))

        self.quadratic_action = toolbar.addAction("Quadratic")
        self.quadratic_action.setCheckable(True)
        self.cubic_action = toolbar.addAction("Cubic")
        self.cubic_action.setCheckable(True)

        self.degree_group = QActionGroup(self)
        self.degree_group.setExclusive(True)
        self.degree_group.addAction(self.quadratic_action)
        self.degree_group.addAction(self.cubic_action)
        self.quadratic_action.setChecked(True)

        self.cubic_action.triggered.connect(lambda: self.scene.set_degree(3))
        self.quadratic_action.triggered.connect(lambda: self.scene.set_degree(2))

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addAction(self.create_action)
        self.mode_group.addAction(self.edit_action)
        self.create_action.setChecked(True)

        self.create_action.triggered.connect(lambda: self.set_mode("create"))
        self.edit_action.triggered.connect(lambda: self.set_mode("edit"))

        toolbar.addSeparator()

        # ---- Zoom ----
        toolbar.addWidget(QLabel(" Zoom: "))
        self.zoom_combo = QComboBox()
        for label, factor in ZOOM_LEVELS:
            self.zoom_combo.addItem(label, factor)
        self.zoom_combo.setCurrentIndex(1)
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_combo)

        toolbar.addSeparator()

        load_action = toolbar.addAction("📂 Load")
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.file_io.load_project)

        save_action = toolbar.addAction("💾 Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.file_io.save_project)
        toolbar.addSeparator()

        # ---- Left group ----
        bg_action = toolbar.addAction("🖼️ Add Background")
        bg_action.triggered.connect(self.file_io.load_background_image)

        color_action = toolbar.addAction("🎨 Curve Color")
        color_action.triggered.connect(self.pick_curve_color)

        self.transparent_action = toolbar.addAction("👻 Make transparent")
        self.transparent_action.setCheckable(True)
        self.transparent_action.setToolTip("Make the selected shape translucent so you can see behind it")
        self.transparent_action.triggered.connect(self.on_transparent_toggled)

        show_all_action = toolbar.addAction("👁️ Show all points")
        show_all_action.setToolTip("Restore all hidden curve points")
        show_all_action.triggered.connect(self.show_all_points)

        mirror_x_action = toolbar.addAction("🪞 Mirror X")
        mirror_x_action.setToolTip(
            "Flip vertically — mirror across the horizontal line through the selection")
        mirror_x_action.triggered.connect(lambda: self.scene.mirror_selection("x"))

        mirror_y_action = toolbar.addAction("🪞 Mirror Y")
        mirror_y_action.setToolTip(
            "Flip horizontally — mirror across the vertical line through the selection")
        mirror_y_action.triggered.connect(lambda: self.scene.mirror_selection("y"))

        generate_action = toolbar.addAction("📄 Show SVG code")
        generate_action.triggered.connect(self.file_io.show_svg_code_dialog)

        export_action = toolbar.addAction("💾 Export SVG")
        export_action.triggered.connect(self.file_io.export_svg)

        # ---- Spacer: pushes the next items to the right ----
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # ---- Right group: Clear All ----
        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

    def _on_zoom_changed(self, index):
        factor = self.zoom_combo.itemData(index)
        self.drawing_view.set_zoom(factor)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        if self.scene.is_transforming():
            self.statusBar().showMessage(
                "Finish the transform first — right-click to validate, Esc to cancel")
            # The toolbar already flipped the check state; put it back.
            if self.scene.mode == "create":
                self.create_action.setChecked(True)
            else:
                self.edit_action.setChecked(True)
            return

        self.log(f"Mode → {mode}")
        if mode == "edit" and self.scene.pending_curve is not None:
            self.scene.discard_current_points()
            self.statusBar().showMessage("Incomplete curve discarded. Switch to Edit mode.")

        self.scene.set_selected_point(None)
        self.scene.clear_hover()
        self.scene.mode = mode
        if mode == "create":
            self.create_action.setChecked(True)
            self.statusBar().showMessage("Create mode: left-click to place points. Right-drag to pan.")
        else:
            self.edit_action.setChecked(True)
            self.statusBar().showMessage("Edit mode: drag points or edit coordinates. Right-drag to pan.")

        self.coord_label.show()

    # ------------------------------------------------------------
    #  Update preview & code
    # ------------------------------------------------------------
    def update_preview(self, svg_string):
        self.preview_widget.set_svg(QByteArray(svg_string.encode()))
        self.refresh_preview_background()

    def refresh_preview_background(self):
        self.preview_widget.set_background(self.scene.background_pixmap)

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()

    def set_status(self, message):
        self.statusBar().showMessage(message)

    def show_all_points(self):
        n = self.scene.show_all_points()
        if n:
            self.statusBar().showMessage(f"👁️ Restored points on {n} curve(s)")
        else:
            self.statusBar().showMessage("Nothing to restore")

    def _step_zoom(self, direction: int):
        idx = self.zoom_combo.currentIndex()
        new_idx = max(0, min(self.zoom_combo.count() - 1, idx + direction))
        if new_idx == idx:
            return
        self.zoom_combo.setCurrentIndex(new_idx)

    def color_selected_shape(self):
        shapes = self.scene.shape_manager.selected_shapes()
        if not shapes:
            self.statusBar().showMessage(
                "No shape selected — hover a curve and press S first")
            return
        initial = shapes[0].color if shapes[0].color is not None \
            else QColor(180, 180, 180)
        title = (f"Color for {shapes[0].name}" if len(shapes) == 1
                 else f"Color for {len(shapes)} shapes")
        color = QColorDialog.getColor(initial, self, title)
        if not color.isValid():
            return
        for shape in shapes:
            self.scene.shape_manager.set_color(shape, color)
        self.log(f"Colored {len(shapes)} shape(s) {color.name()}")

    def pick_curve_color(self):
        color = QColorDialog.getColor(self.scene.curve_color, self, "Curve Color")
        if not color.isValid():
            return
        self.scene.set_curve_color(color)
        self.log(f"Curve color → {color.name()}")

    def on_transparent_toggled(self, checked):
        self.scene.shape_manager.set_transparent(checked)
        self.log(f"Transparent mode: {'on' if checked else 'off'}")

    def _debug_sizes(self):
        pw = self.preview_widget
        print("=== PreviewWidget ===")
        print(f"  size:            {pw.width()} x {pw.height()}")
        print(f"  minimumSizeHint: {pw.minimumSizeHint().width()} x {pw.minimumSizeHint().height()}")

        tb = pw._toolbar
        print(f"  toolbar size:    {tb.width()} x {tb.height()}")
        print(f"  toolbar sizeHint:{tb.sizeHint().width()} x {tb.sizeHint().height()}")

        scroll = pw._scroll
        vp = scroll.viewport()
        print(f"  scroll size:     {scroll.width()} x {scroll.height()}")
        print(f"  scroll viewport: {vp.width()} x {vp.height()}   <-- white area")
        print(f"  scroll frame w:  {scroll.frameWidth()}")

        vbar = scroll.verticalScrollBar()
        hbar = scroll.horizontalScrollBar()
        print(f"  vScrollBar:      visible={vbar.isVisible()}, width={vbar.width()}")
        print(f"  hScrollBar:      visible={hbar.isVisible()}, height={hbar.height()}")

        canvas = pw._canvas
        cs = canvas.content_size()
        print(f"  canvas size:     {canvas.width()} x {canvas.height()}")
        print(f"  content_size:    {cs.width():.1f} x {cs.height():.1f}")
        print(f"  zoom:            {pw._zoom}")
        print(f"  base_scale:      {pw._base_scale():.4f}")

        print("=== Right column ===")
        print(f"  preset_panel:    {self.preset_panel.width()} x {self.preset_panel.height()}")
        print(f"  info_panel:      {self.info_panel.width()} x {self.info_panel.height()}")
        print(f"  window:          {self.width()} x {self.height()}")