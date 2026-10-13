# main_window.py
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QColorDialog, QComboBox, QSizePolicy, QMenu, QToolButton, QDialog
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QColor, QShortcut, QKeySequence

from core.settings import DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT

from scene.bezier_scene import BezierScene
from ui.custom_view import CustomGraphicsView
from ui.info_panel import InfoPanel
from core.file_io import FileIO
from ui.preview_widget import PreviewWidget
from ui.preset_panel import PresetPanel
from ui.shortcuts_dialog import ShortcutsDialog
from ui.save_shape_dialog import SaveShapeDialog

ZOOM_LEVELS = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0), ("8x", 8.0), ("16x", 16.0)]
POINT_TIP_GAP = 22  # viewport pixels above the point's centre

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
        self._key_handlers = self._build_key_handlers()
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

        self._hovered_pt = None

        self.point_tip = QLabel(self.drawing_view.viewport())
        self.point_tip.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; "
            "padding: 2px 5px; border-radius: 3px; font-weight: bold;"
        )
        self.point_tip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.point_tip.hide()

        # ---- Connect signals ----
        self.scene.svgCodeChanged.connect(self.update_preview)
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)
        self.drawing_view.mouseMoved.connect(self.scene.on_mouse_moved)
        self.scene.transformModeChanged.connect(self.drawing_view.set_transform_mode)
        self.drawing_view.transformLeftClick.connect(self.scene.end_transform)
        self.preset_panel.presetRequested.connect(self.scene.arm_preset)
        self.scene.presetStateChanged.connect(self.preset_panel.sync_state)
        self.drawing_view.shiftReleased.connect(self.scene.on_shift_released)
        self.preview_widget.showSvgRequested.connect(self.file_io.show_svg_code_dialog)
        self.scene.hoveredPointChanged.connect(self.show_point_tip)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()

    def _build_key_handlers(self) -> dict:
        K = Qt.Key
        Shift = Qt.KeyboardModifier.ShiftModifier
        scene = self.scene
        return {
            K.Key_Escape: self._handle_escape,
            K.Key_R: lambda e: scene.start_rotation(),
            K.Key_B: lambda e: scene.start_scaling(),
            K.Key_M: lambda e: scene.start_move(),
            K.Key_L: lambda e: scene.link_manager.try_link_proximity(),
            K.Key_S: lambda e: scene.selection.select_shape_from_hover(add=bool(e.modifiers() & Shift)),
            K.Key_C: self._handle_color_selected_shape,
            K.Key_H: lambda e: scene.hide_hovered_curve_points(),
            K.Key_A: lambda e: scene.select_curve_under_hover(add=bool(e.modifiers() & Shift)),
            K.Key_X: lambda e: scene.mirror_selection("x"),
            K.Key_Y: lambda e: scene.mirror_selection("y"),
            K.Key_U: lambda e: scene.link_manager.try_break_junction(),
            K.Key_Plus: lambda e: self._step_zoom(+1),
            K.Key_Equal: lambda e: self._step_zoom(+1),
            K.Key_Minus: lambda e: self._step_zoom(-1),
            K.Key_Backspace: lambda e: scene.delete_selection(),
            K.Key_Left: lambda e: scene.move_selected_points(-1, 0),
            K.Key_Right: lambda e: scene.move_selected_points(+1, 0),
            K.Key_Up: lambda e: scene.move_selected_points(0, -1),
            K.Key_Down: lambda e: scene.move_selected_points(0, +1),
        }

    def _handle_escape(self, event) -> bool:
        if self.scene.is_transforming():
            self.scene.end_transform(commit=False)
            return True
        if self.scene.cancel_preset():
            return True
        self.scene.clear_selection()
        return self.scene.cancel_pending_curve()

    def _handle_color_selected_shape(self, event) -> bool:
        self.color_selected_shape()
        return True

    def _toggle_mode(self):
        new_mode = "edit" if self.scene.mode == "create" else "create"
        self.set_mode(new_mode)

    def keyPressEvent(self, event):
        handler = self._key_handlers.get(event.key())
        if handler is not None and handler(event):
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
            self.point_tip.hide()
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
        self._reposition_point_tip()

    def show_point_tip(self, pt):
        self._hovered_pt = pt
        self._reposition_point_tip()

    def _reposition_point_tip(self):
        pt = self._hovered_pt
        if pt is None:
            self.point_tip.hide()
            return
        pos = pt.pos()
        self.point_tip.setText(f"({pos.x():.1f}, {pos.y():.1f})")
        self.point_tip.adjustSize()

        vp = self.drawing_view.mapFromScene(pos)
        x = vp.x() - self.point_tip.width() // 2
        y = max(0, vp.y() - self.point_tip.height() - POINT_TIP_GAP)
        self.point_tip.move(x, y)
        self.point_tip.show()
        self.point_tip.raise_()
    # ------------------------------------------------------------
    #  Toolbar
    # ------------------------------------------------------------
    def _setup_toolbar(self):
        toolbar = self.addToolBar("Tools")

        # ---- Mode ----
        toolbar.addWidget(QLabel(" Mode: "))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Create", "create")
        self.mode_combo.addItem("Edit", "edit")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_combo)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Type: "))
        self.degree_combo = QComboBox()
        self.degree_combo.addItem("Quadratic", 2)
        self.degree_combo.addItem("Cubic", 3)
        self.degree_combo.currentIndexChanged.connect(self._on_degree_changed)
        toolbar.addWidget(self.degree_combo)

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

        # ---- Files menu ----
        files_btn = QToolButton()
        files_btn.setText("📁 Files")
        files_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        files_menu = QMenu(files_btn)

        load_action = files_menu.addAction("📂 Load")
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.file_io.load_project)

        save_action = files_menu.addAction("💾 Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.file_io.save_project)

        bg_action = files_menu.addAction("🖼️ Add Background")
        bg_action.triggered.connect(self.file_io.load_background_image)

        export_action = files_menu.addAction("💾 Export SVG")
        export_action.triggered.connect(self.file_io.export_svg)

        save_shape_action = files_menu.addAction("📐 Save Shape")
        save_shape_action.setToolTip("Save the selected shape, chain, or curve as a reusable preset")
        save_shape_action.triggered.connect(self.save_selected_shape)

        files_btn.setMenu(files_menu)
        toolbar.addWidget(files_btn)

        # ---- Effects menu ----
        effects_btn = QToolButton()
        effects_btn.setText("✨ Effects")
        effects_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        effects_menu = QMenu(effects_btn)

        mirror_x_action = effects_menu.addAction("🪞 Mirror X")
        mirror_x_action.setToolTip("Flip vertically — mirror across the horizontal line through the selection")
        mirror_x_action.triggered.connect(lambda: self.scene.mirror_selection("x"))

        mirror_y_action = effects_menu.addAction("🪞 Mirror Y")
        mirror_y_action.setToolTip("Flip horizontally — mirror across the vertical line through the selection")
        mirror_y_action.triggered.connect(lambda: self.scene.mirror_selection("y"))

        effects_menu.addSeparator()

        self.transparent_action = effects_menu.addAction("👻 Make transparent")
        self.transparent_action.setCheckable(True)
        self.transparent_action.setToolTip("Make the selected shape translucent so you can see behind it")
        self.transparent_action.triggered.connect(self.on_transparent_toggled)

        effects_btn.setMenu(effects_menu)
        toolbar.addWidget(effects_btn)

        toolbar.addSeparator()
        color_action = toolbar.addAction("🎨 Curve Color")
        color_action.triggered.connect(self.pick_curve_color)

        show_all_action = toolbar.addAction("👁️ Show all points")
        show_all_action.setToolTip("Restore all hidden curve points")
        show_all_action.triggered.connect(self.show_all_points)

        shortcuts_action = toolbar.addAction("⌨️ Shortcuts")
        shortcuts_action.setToolTip("Show all keyboard shortcuts")
        shortcuts_action.triggered.connect(self.show_shortcuts)

        # ---- Spacer: pushes the next items to the right ----
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # ---- Right group: Clear All ----
        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

    def _on_zoom_changed(self, index):
        factor = self.zoom_combo.itemData(index)
        self.drawing_view.set_zoom(factor)

    def _on_degree_changed(self, index):
        self.scene.set_degree(self.degree_combo.itemData(index))

    def _on_mode_changed(self, index):
        self.set_mode(self.mode_combo.itemData(index))

    def _sync_mode_combo(self):
        """Reflect scene.mode in the combo without re-firing set_mode."""
        target = 0 if self.scene.mode == "create" else 1
        if self.mode_combo.currentIndex() == target:
            return
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(target)
        self.mode_combo.blockSignals(False)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        if self.scene.is_transforming():
            self.statusBar().showMessage(...)
            self._sync_mode_combo()
            return

        self.log(f"Mode → {mode}")
        if mode == "edit" and self.scene.pending_curve is not None:
            self.scene.discard_current_points()
            self.statusBar().showMessage("Incomplete curve discarded. Switch to Edit mode.")

        self.scene.set_selected_point(None)
        self.scene.clear_hover()
        self.scene.mode = mode
        self._sync_mode_combo()
        if mode == "create":
            self.statusBar().showMessage("Create mode: left-click to place points. Right-drag to pan.")
        else:
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

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    def save_selected_shape(self):
        kind, curves = self.scene.selection.exportable_selection()
        if not curves:
            self.statusBar().showMessage(
                "Select exactly one shape, chain, or curve first")
            return

        description = self._describe_curves(curves)
        default_name = f"{kind.capitalize()} {curves[0].id}"
        dialog = SaveShapeDialog(description, default_name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        name, tooltip = dialog.values()
        self.file_io.save_user_shape(name, tooltip, kind, curves)

    @staticmethod
    def _describe_curves(curves) -> str:
        lines = []
        for c in curves:
            pts = ", ".join(
                f"({p.pos().x():.1f}, {p.pos().y():.1f})" for p in c.points)
            lines.append(f"{c.name}: points: ({pts})")
        return "\n".join(lines)

    def set_status(self, message):
        self.statusBar().showMessage(message)

    def show_all_points(self):
        n = self.scene.show_all_points()
        if n:
            self.statusBar().showMessage(f"👁️ Restored points on {n} curve(s)")
        else:
            self.statusBar().showMessage("Nothing to restore")

    def _step_zoom(self, direction: int) -> bool:
        idx = self.zoom_combo.currentIndex()
        new_idx = max(0, min(self.zoom_combo.count() - 1, idx + direction))
        if new_idx != idx:
            self.zoom_combo.setCurrentIndex(new_idx)
        return True

    def color_selected_shape(self):
        shapes = self.scene.selection.selected_shapes()
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
