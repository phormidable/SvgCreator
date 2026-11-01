# ui/main_window.py
from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QColorDialog, QDialog, QMessageBox
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QColor, QShortcut, QKeySequence

from core.settings import DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT

from scene.bezier_scene import BezierScene
from ui.elements.custom_view import CustomGraphicsView
from ui.elements.info_panel import InfoPanel
from core.file_io import FileIO
from ui.elements.preview_widget import PreviewWidget
from ui.elements.preset_panel import PresetPanel
from ui.dialogs.save_shape_dialog import SaveShapeDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.shortcuts_dialog import ShortcutsDialog
from ui.elements.main_toolbar import MainToolBar

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
        self.toolbar = MainToolBar(self)

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
        self.preset_panel.presetRequested.connect(self.scene.presets.arm_preset)
        self.scene.presetStateChanged.connect(self.preset_panel.sync_state)
        self.drawing_view.shiftReleased.connect(self.scene.presets.on_shift_released)
        self.preview_widget.showSvgRequested.connect(self.file_io.show_svg_code_dialog)
        self.scene.hoveredPointChanged.connect(self.show_point_tip)
        self.scene.transformTypedChanged.connect(lambda text: self.statusBar().showMessage( f"Rotate: {text}°" if text else ""))
        self.scene.undoStateChanged.connect(self._refresh_undo_actions)
        self.drawing_view.zoomChanged.connect(self.toolbar.sync_zoom)

        self._refresh_undo_actions()
        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()

    def update_title(self):
        """Update the window title to show the current filename."""
        if self.file_io.current_file:
            filename = Path(self.file_io.current_file).name
            self.setWindowTitle(f"{filename} - SvgCreator")
        else:
            self.setWindowTitle("SvgCreator")

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
        undo, redo = self.toolbar.undo_action, self.toolbar.redo_action
        undo.setEnabled(u.can_undo())
        redo.setEnabled(u.can_redo())
        undo.setToolTip(f"Undo: {u.undo_label()}" if u.can_undo() else "Nothing to undo")
        redo.setToolTip(f"Redo: {u.redo_label()}" if u.can_redo() else "Nothing to redo")

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
            K.Key_S: lambda e: scene.selection_ops.select_shape_from_hover(add=bool(e.modifiers() & Shift)),
            K.Key_H: always(scene.hide_points),
            K.Key_A: self._handle_a_key,
            K.Key_C: self._handle_c_key,
            K.Key_V: self._handle_v_key,
            K.Key_X: always(lambda: scene.mirror_selection("x")),
            K.Key_Y: self._handle_y_key,
            K.Key_Z: self._handle_z_key,
            K.Key_U: always(scene.link_manager.try_break_junction),
            K.Key_Equal: always(lambda: self.toolbar.step_zoom(+1)),
            K.Key_Minus: always(lambda: self.toolbar.step_zoom(-1)),
            K.Key_Backspace: always(scene.delete_selection),
            K.Key_Left: lambda e: self._arrow_nudge(-1, 0, e),
            K.Key_Right: lambda e: self._arrow_nudge(+1, 0, e),
            K.Key_Up: lambda e: self._arrow_nudge(0, -1, e),
            K.Key_Down: lambda e: self._arrow_nudge(0, +1, e),
            K.Key_J: self._handle_j_key,
        }

    def _handle_escape(self, event) -> bool:
        if self.scene.is_transforming():
            self.scene.end_transform(commit=False)
            return True
        if self.scene.presets.cancel_preset():
            return True
        self.scene.mouse.abort_interaction()
        self.scene.clear_selection()
        return self.scene.builder.cancel_pending_curve()

    def _handle_a_key(self, event) -> bool:
        """Ctrl+A toggles select-all; plain A selects the hovered curve."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return self.scene.selection_ops.toggle_select_all()
        add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        return self.scene.select_curve_under_hover(add=add)

    def _handle_c_key(self, event) -> bool:
        """Ctrl+C copies; plain C opens the colour picker."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return self.scene.clipboard.copy()
        self.color_selected_shape()
        return True

    def _handle_j_key(self, event) -> bool:
        """J connects the two selected points with a straight line.
        Ctrl+J does the same and links the new line's endpoints to the sources."""
        link = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        return self.scene.selection_ops.join_with_line(link=link)

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
        if self.scene.transform.handle_key(event):
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

    def open_settings_dialog(self):
        current_bg = self.scene.background.path or ""
        settings = {
            "canvas_width": int(self.scene.viewbox.width()),
            "canvas_height": int(self.scene.viewbox.height()),
            "stroke_width": self.scene.stroke_width,
            "curve_color": self.scene.curve_color,
            "background_path": current_bg,
            "json_dir": self.file_io.json_dir,
            "svg_dir": self.file_io.svg_dir,
        }
        dialog = SettingsDialog(settings, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_values = dialog.values()
        changes = []

        # ---- Canvas size ----
        if (new_values["canvas_width"] != int(self.scene.viewbox.width())
                or new_values["canvas_height"] != int(self.scene.viewbox.height())):
            self.scene.set_viewbox(new_values["canvas_width"], new_values["canvas_height"])
            changes.append(f"Canvas {new_values['canvas_width']}×{new_values['canvas_height']}")

        # ---- Stroke width ----
        if new_values["stroke_width"] != self.scene.stroke_width:
            self.scene.stroke_width = new_values["stroke_width"]
            if self.scene.builder.current_stroke_width is not None:
                self.scene.builder.set_curve_style(
                    self.scene.builder.current_degree, is_stroke=True)
            changes.append(f"Stroke {new_values['stroke_width']}")

        # ---- Curve color ----
        new_color = QColor(new_values["curve_color"])
        if new_color.isValid() and new_color != self.scene.curve_color:
            self.scene.set_curve_color(new_color)
            changes.append(f"Color {new_color.name()}")

        # ---- Background ----
        old_bg = self.scene.background.path
        new_bg = new_values["background_path"]
        if new_bg != old_bg:
            if new_bg is None:
                if old_bg is not None:
                    self.scene.background.remove()
                    self.refresh_preview_background()
                    changes.append("Background removed")
            else:
                if self.scene.load_background_image(new_bg):
                    self.refresh_preview_background()
                    changes.append("Background loaded")
                else:
                    QMessageBox.warning(self, "Background",
                                        f"Could not load:\n{new_bg}")

        # ---- File paths ----
        self.file_io.json_dir = new_values["json_dir"]
        self.file_io.svg_dir = new_values["svg_dir"]

        # ---- Summary ----
        if changes:
            msg = "Settings updated: " + " | ".join(changes)
            self.statusBar().showMessage(msg)
            self.log(msg)
            # Push a single undo entry for all changes
            self.scene.undo.push("Settings")
        else:
            self.statusBar().showMessage("No changes")


    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        if self.scene.is_transforming():
            self.statusBar().showMessage("Transformation going on - mode not changed.")
            self.toolbar.sync_mode(self.scene.mode)
            return

        self.log(f"Mode → {mode}")
        if mode == "edit" and self.scene.pending_curve is not None:
            self.scene.builder.discard()
            self.statusBar().showMessage("Incomplete curve discarded. Switch to Edit mode.")

        self.scene.set_selected_point(None)
        self.scene.clear_hover()
        self.scene.mode = mode
        self.toolbar.sync_mode(self.scene.mode)
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
        self.scene.undo.push("Clear all")
        self.file_io.current_file = None  # NEW
        self.update_title()

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    def save_selected_shape(self):
        kind, curves = self.scene.selection_ops.exportable_selection()
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

    def hide_selection(self):
        if self.scene.hide_points():
            self.statusBar().showMessage("🙈 Points hidden")
        else:
            self.statusBar().showMessage(
                "Nothing to hide — select points or hover a curve")

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