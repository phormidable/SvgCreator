# ui/main_window.py
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QColorDialog, QComboBox, QSizePolicy, QMenu, QToolButton, QDialog
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QColor, QShortcut, QKeySequence

from core.settings import (DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT, PREVIEW_WIDTH, ZOOM_LEVELS,
    PREVIEW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT, GRID_SIZE_OPTIONS, GRID_DEFAULT_SPACING, TOOLBAR_CHECKED_STYLE)

from scene.bezier_scene import BezierScene
from ui.custom_view import CustomGraphicsView
from ui.info_panel import InfoPanel
from core.file_io import FileIO
from ui.preview_widget import PreviewWidget
from ui.preset_panel import PresetPanel
from ui.shortcuts_dialog import ShortcutsDialog
from ui.save_shape_dialog import SaveShapeDialog

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
        self.scene.transformTypedChanged.connect(lambda text: self.statusBar().showMessage( f"Rotate: {text}°" if text else ""))
        self.scene.undoStateChanged.connect(self._refresh_undo_actions)

        self._refresh_undo_actions()
        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()

    def _do_undo(self):
        # Intercept: undo during an in-flight gesture cancels the gesture,
        # it does not walk the history.
        if self.scene.pending_curve is not None:
            self.scene.builder.discard()
            return
        if self.scene.is_transforming():
            self.scene.end_transform(commit=False)
            return
        label = self.scene.undo.undo()
        self.statusBar().showMessage(f"Undid: {label}" if label else "Nothing to undo")

    def _do_redo(self):
        # Match undo's intercept: mid-gesture redo cancels the gesture, it
        # does not walk the history.
        if self.scene.pending_curve is not None:
            self.scene.builder.discard()
            return
        if self.scene.is_transforming():
            self.scene.end_transform(commit=False)
            return
        label = self.scene.undo.redo()
        self.statusBar().showMessage(f"Redid: {label}" if label else "Nothing to redo")

    def _refresh_undo_actions(self):
        u = self.scene.undo
        self.undo_action.setEnabled(u.can_undo())
        self.redo_action.setEnabled(u.can_redo())
        self.undo_action.setToolTip(
            f"Undo: {u.undo_label()}" if u.can_undo() else "Nothing to undo")
        self.redo_action.setToolTip(
            f"Redo: {u.redo_label()}" if u.can_redo() else "Nothing to redo")

    def _handle_z_key(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._do_redo()
        else:
            self._do_undo()
        return True

    def _handle_y_key(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._do_redo()
            return True
        return self.scene.mirror_selection("y")

    @staticmethod
    def _always(fn):
        """Wrap a no-argument action so it satisfies the key-handler contract:
        runs the action, returns True to signal 'handled'."""

        def handler(_event):
            fn()
            return True

        return handler

    def _arrow_nudge(self, dx: int, dy: int, event) -> bool:
        """Move the selection by 1 unit, or 10 when Shift is held."""
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        if self.scene.move_selected_points(dx * step, dy * step):
            arrow = {(1, 0): "→", (-1, 0): "←", (0, -1): "↑", (0, 1): "↓"}[(dx, dy)]
            self.scene.undo.push(f"Nudge {arrow}")
        return True

    def _build_key_handlers(self) -> dict:
        K = Qt.Key
        Shift = Qt.KeyboardModifier.ShiftModifier
        scene = self.scene
        always = self._always
        return {
            K.Key_Escape: self._handle_escape,
            K.Key_R: always(scene.transform.start_rotation),
            K.Key_B: always(scene.transform.start_scaling),
            K.Key_M: always(scene.transform.start_move),
            K.Key_L: always(scene.link_manager.try_link_proximity),
            K.Key_S: lambda e: scene.selection.select_shape_from_hover(add=bool(e.modifiers() & Shift)),
            #K.Key_C: always(self.color_selected_shape),
            K.Key_H: always(scene.hide_points),
            K.Key_A: self._handle_a_key,
            K.Key_C: self._handle_c_key,
            K.Key_V: self._handle_v_key,
            K.Key_X: always(lambda: scene.mirror_selection("x")),
            #K.Key_Y: always(lambda: scene.mirror_selection("y")),
            K.Key_Y: self._handle_y_key,
            K.Key_Z: self._handle_z_key,
            K.Key_U: always(scene.link_manager.try_break_junction),
            K.Key_Plus: always(lambda: self._step_zoom(+1)),
            K.Key_Equal: always(lambda: self._step_zoom(+1)),
            K.Key_Minus: always(lambda: self._step_zoom(-1)),
            K.Key_Backspace: always(scene.delete_selection),
            K.Key_Left: lambda e: self._arrow_nudge(-1, 0, e),
            K.Key_Right: lambda e: self._arrow_nudge(+1, 0, e),
            K.Key_Up: lambda e: self._arrow_nudge(0, -1, e),
            K.Key_Down: lambda e: self._arrow_nudge(0, +1, e),
        }

    def _handle_escape(self, event) -> bool:
        if self.scene.is_transforming():
            self.scene.end_transform(commit=False)
            return True
        if self.scene.cancel_preset():
            return True
        self.scene.clear_selection()
        return self.scene.cancel_pending_curve()

    def _handle_a_key(self, event) -> bool:
        """Ctrl+A toggles select-all; plain A selects the hovered curve."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return self.scene.selection.toggle_select_all()
        add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        return self.scene.select_curve_under_hover(add=add)

    def _handle_c_key(self, event) -> bool:
        """Ctrl+C copies; plain C opens the colour picker."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return self.scene.clipboard.copy()
        self.color_selected_shape()
        return True

    def _handle_v_key(self, event) -> bool:
        """Ctrl+V pastes at the current cursor position (no snap)."""
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False  # plain V is unbound
        pos = self.scene.mouse.last_scene_pos or self.scene.viewbox.center()
        self.scene.clipboard.paste(pos)
        return True

    def _toggle_mode(self):
        new_mode = "edit" if self.scene.mode == "create" else "create"
        self.set_mode(new_mode)

    def keyPressEvent(self, event):
        if self.scene.handle_transform_key(event):
            event.accept()
            return
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

        if self.scene.grid_item.snap_enabled:
            snapped = self.scene.grid_item.snap_to(scene_pos)
            text = f"({snapped.x():.0f}, {snapped.y():.0f})"
        else:
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
        pos = pt.model_pos()
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

        # ---- Undo / Redo ----
        self.undo_action = toolbar.addAction("↶")
        self.undo_action.setToolTip("Undo (Ctrl+Z)")
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self._do_undo)

        self.redo_action = toolbar.addAction("↷")
        self.redo_action.setToolTip("Redo (Ctrl+Shift+Z / Ctrl+Y)")
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self._do_redo)

        toolbar.addSeparator()
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

        # ---- Grid ----
        self.grid_action = toolbar.addAction("Show Grid")
        self.grid_action.setCheckable(True)
        self.grid_action.toggled.connect(self._on_grid_toggled)

        grid_btn = toolbar.widgetForAction(self.grid_action)
        if grid_btn is not None:
            grid_btn.setStyleSheet(TOOLBAR_CHECKED_STYLE)

        toolbar.addWidget(QLabel(" Grid size: "))
        self.grid_combo = QComboBox()
        for label, spacing in GRID_SIZE_OPTIONS:
            self.grid_combo.addItem(label, spacing)
        for i in range(self.grid_combo.count()):
            if self.grid_combo.itemData(i) == GRID_DEFAULT_SPACING:
                self.grid_combo.setCurrentIndex(i)
                break
        self.grid_combo.currentIndexChanged.connect(self._on_grid_size_changed)
        toolbar.addWidget(self.grid_combo)

        # Start with the grid shown (for testing). This fires toggled(True) —
        # make sure it happens *after* the connect above.
        self.grid_action.setChecked(True)

        self.snap_action = toolbar.addAction("Snap to Grid")
        self.snap_action.setCheckable(True)
        self.snap_action.toggled.connect(self.scene.set_snap_enabled)

        # Colour the checked state red. widgetForAction returns the QToolButton
        # that represents this action on the toolbar.
        snap_btn = toolbar.widgetForAction(self.snap_action)
        if snap_btn is not None:
            snap_btn.setStyleSheet(TOOLBAR_CHECKED_STYLE)

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

        center_h_action = effects_menu.addAction("↔ Center H")
        center_h_action.setToolTip("Centre the selection horizontally in the viewbox")
        center_h_action.triggered.connect(lambda: self.scene.center_selection("horizontal"))

        center_v_action = effects_menu.addAction("↕ Center V")
        center_v_action.setToolTip("Centre the selection vertically in the viewbox")
        center_v_action.triggered.connect(lambda: self.scene.center_selection("vertical"))

        effects_menu.addSeparator()

        self.transparent_action = effects_menu.addAction("👻 Make transparent")
        self.transparent_action.setCheckable(True)
        self.transparent_action.setToolTip("Make the selected shape translucent so you can see behind it")
        self.transparent_action.triggered.connect(self.on_transparent_toggled)

        snap_action = effects_menu.addAction("📐 Quantize Selection")
        snap_action.setToolTip("Move every selected point to the nearest grid line")
        snap_action.triggered.connect(self.snap_selection_to_grid)

        effects_btn.setMenu(effects_menu)
        toolbar.addWidget(effects_btn)

        # ---- Settings menu ----
        settings_btn = QToolButton()
        settings_btn.setText("⚙️ Settings")
        settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_menu = QMenu(settings_btn)

        settings_menu.addSeparator()

        curve_color_action = settings_menu.addAction("🎨 Curve Color")
        curve_color_action.setToolTip("Set the default colour for new and unshaped curves")
        curve_color_action.triggered.connect(self.pick_curve_color)

        settings_menu.addSeparator()

        add_bg_action = settings_menu.addAction("🖼️ Add Background")
        add_bg_action.setToolTip("Load a reference image behind the curves")
        add_bg_action.triggered.connect(self.file_io.load_background_image)

        remove_bg_action = settings_menu.addAction("🚫 Remove Background")
        remove_bg_action.setToolTip("Remove the current background image")
        remove_bg_action.triggered.connect(self.remove_background)

        settings_btn.setMenu(settings_menu)
        toolbar.addWidget(settings_btn)

        show_all_action = toolbar.addAction("👁️ Show all points")
        show_all_action.setToolTip("Restore all hidden curve points")
        show_all_action.triggered.connect(self.show_all_points)

        # ---- Spacer: pushes the next items to the right ----
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        shortcuts_action = toolbar.addAction("⌨️ Shortcuts")
        shortcuts_action.setToolTip("Show all keyboard shortcuts")
        shortcuts_action.triggered.connect(self.show_shortcuts)

        # ---- Right group: Clear All ----
        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

    def _test_push(self):
        self.scene.undo.push("manual push")
        self.statusBar().showMessage(
            f"Snapshot pushed. Stack: {self.scene.undo.describe()}")

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

    def _on_grid_toggled(self, checked: bool):
        self.grid_action.setText("Hide Grid" if checked else "Show Grid")
        self.scene.set_grid_visible(checked)

    def _on_grid_size_changed(self, index: int):
        spacing = self.grid_combo.itemData(index)
        self.scene.set_grid_spacing(spacing)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        if self.scene.is_transforming():
            self.statusBar().showMessage("Transformation going on - mode not changed.")
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

    def remove_background(self):
        if self.scene.background.path is None:
            self.statusBar().showMessage("No background to remove")
            return
        self.scene.background.remove()
        self.refresh_preview_background()
        self.statusBar().showMessage("Background removed")
        self.log("Background removed")

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()
        self.scene.undo.push("Clear all")

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
            self.statusBar().showMessage("No shape selected — hover a curve and press S first")
            return

        initial = shapes[0].color if shapes[0].color is not None else QColor(180, 180, 180)
        title = (f"Color for {shapes[0].name}" if len(shapes) == 1 else f"Color for {len(shapes)} shapes")
        color = QColorDialog.getColor(initial, self, title)

        if not color.isValid():
            return

        if all(s.color is not None and s.color == color for s in shapes):
            return  # every selected shape already this colour

        for shape in shapes:
            self.scene.shape_manager.set_color(shape, color)
        self.log(f"Colored {len(shapes)} shape(s) {color.name()}")
        self.scene.undo.push(f"Color {len(shapes)} shape(s)")

    def pick_curve_color(self):
        color = QColorDialog.getColor(self.scene.curve_color, self, "Curve Color")
        if not color.isValid():
            return
        if color == self.scene.curve_color:
            return  # no change
        self.scene.set_curve_color(color)
        self.log(f"Curve color → {color.name()}")
        self.scene.undo.push("Curve color")

    def on_transparent_toggled(self, checked):
        self.scene.shape_manager.set_transparent(checked)
        self.log(f"Transparent mode: {'on' if checked else 'off'}")

    def snap_selection_to_grid(self):
        if not self.scene.selected_points:
            self.statusBar().showMessage("Nothing to snap — select points first")
            return
        n = self.scene.snap_selection_to_grid()
        self.statusBar().showMessage(
            f"Snapped {n} point(s) to grid" if n else "Already on grid")