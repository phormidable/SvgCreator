# bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter, QColor, QBrush
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsEllipseItem
from PySide6.QtSvg import QSvgRenderer

from settings import (ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH,
                      DEFAULT_CURVE_COLOR, ROTATION_PIVOT_RADIUS, ROTATION_PIVOT_COLOR, HOVER_TOLERANCE, MOON_PRESETS)

from link_manager import LinkManager
from control_point import ControlPoint
from bezier_curve import BezierCurve
import scene_io
import math
from shape_manager import ShapeManager

SHAPE_FILL_Z = -10

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()
    curveListChanged = Signal()
    curveSelected = Signal(int)
    curveDragFinished = Signal()
    messageLogged = Signal(str)
    rotationModeChanged = Signal(bool)

    def __init__(self):
        super().__init__()

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT   # full working area (scene rect)
        self.viewbox = VIEWBOX_RECT     # region that gets exported

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        self.pending_curve = None     # BezierCurve currently being placed
        self.mode = "create"
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selected_points: list[ControlPoint] = []
        self.selected_curve_idx = -1
        self.dragging_point = None
        self.focused_point: ControlPoint | None = None
        self.hovered_curve = None
        self._ensuring_visible = False
        self.background_item = None
        self.background_image_path = None
        self.background_pixmap = None
        self._preset_pending: str | None = None

        self._drag_targets: dict[ControlPoint, QPointF] = {}
        self._drag_primary_start: QPointF | None = None

        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)
        self.link_manager = LinkManager(self)
        self.shape_manager = ShapeManager(self)

        self._rotation_pivot: QPointF | None = None
        self._rotation_ref_angle: float | None = None
        self._rotation_starts: dict[ControlPoint, QPointF] = {}
        self._rotation_pivot_item: QGraphicsEllipseItem | None = None

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # A pending preset consumes this click, whatever the mode.
        if self._preset_pending is not None:
            self._place_preset(event.scenePos())
            return

        # ---- Create mode: left-click places a point, nothing else ----
        if self.mode == "create":
            if self.pending_curve is None:
                self.pending_curve = BezierCurve(self)
            self.pending_curve.add_point(event.scenePos())
            if self.pending_curve.is_complete():
                self.finalize_curve()
                self.messageLogged.emit(f"Curve created")
            return

        # ---- Edit mode ----
        views = self.views()
        if not views:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.scenePos(), views[0].transform())

        if isinstance(item, ControlPoint) and item.curve.committed:
            curve = item.curve
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if shift:
                self.toggle_selection(item)
                self.clear_hover()
                event.accept()
                return

            # Non-shift: selection collapses to exactly this point.
            self.set_selected_point(item)

            self.clear_hover()
            # Setting dragging_point *before* calling super() is deliberate:
            # Qt delivers the first mouseMoveEvent after this returns, and
            # mouseMoveEvent only mirrors the drag when dragging_point is set.
            # _start_drag snapshots _drag_primary_start here, before Qt moves
            # the primary point, so the delta is measured from the pre-drag
            # position.
            self.dragging_point = item
            self._start_drag(item)
            idx = self.curves.index(curve)
            if idx != self.selected_curve_idx:
                self.selected_curve_idx = idx
                self.curveSelected.emit(idx)
            super().mousePressEvent(event)
            return

        # Not on a point. Refresh hover for this exact scene position —
        # mouseMoved normally keeps it current, but a click without a
        # preceding move shouldn't be a no-op.
        self._update_hover(event.scenePos())
        if self.hovered_curve is not None:
            add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.select_curve_under_hover(add=add)
            event.accept()
            return

        # Nothing under the cursor → drop selection.
        self.set_selected_point(None)
        super().mousePressEvent(event)

    def _with_linked(self, points) -> set[ControlPoint]:
        """Return `points` plus every link-group sibling of any of them."""
        result = set(points)
        for pt in points:
            group = self.link_manager.group_of(pt)
            if group:
                result.update(group)
        return result

    def _start_drag(self, primary):
        primary_group = self._with_linked({primary})
        seeds = set(self.selected_points) | {primary}
        self._drag_targets = {pt: pt.pos()
                              for pt in self._with_linked(seeds) - primary_group}
        self._drag_primary_start = primary.pos()


    # ------------------------------------------------------------
    #  Shape detection
    # ------------------------------------------------------------

    def cancel_pending_curve(self) -> bool:
        if self.mode == "create" and self.pending_curve is not None:
            self.discard_current_points()
            return True
        return False

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        if self.dragging_point is not None:
            # Qt just moved the primary; mirror its delta onto the rest.
            delta = self.dragging_point.pos() - self._drag_primary_start
            for pt, start in self._drag_targets.items():
                pt.setPos(start + delta)
            self.link_manager.update_proximity(self.dragging_point)

        if self.dragging_point is None or self._ensuring_visible:
            return
        self._ensuring_visible = True
        try:
            pos = event.scenePos()
            target = QRectF(pos.x() - 1, pos.y() - 1, 2, 2)
            for view in self.views():
                view.ensureVisible(target, 60, 60)
        finally:
            self._ensuring_visible = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging_point is not None:
                #self.dragging_point.curve.set_highlighted(False)
                self.dragging_point = None
                self._drag_targets = {}
                self._drag_primary_start = None
                self.link_manager.clear_proximity()
                self._update_hover(event.scenePos())
                self.curveDragFinished.emit()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Hover tracking
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        if self.is_rotating():
            self._update_rotation(scene_pos)
            return
        if self.dragging_point is not None:
            return
        if self.mode == "create":
            return  # no hover in create mode
        self._update_hover(scene_pos)

    def _update_hover(self, pos):
        new_hovered = None
        new_focused_pt = None

        if pos is not None:
            tol2 = HOVER_TOLERANCE * HOVER_TOLERANCE
            for curve in reversed(self.curves):
                if not curve.is_near(pos):
                    continue
                new_hovered = curve
                # Is a point of THIS curve under the cursor?
                for pt in curve.points:
                    p = pt.pos()
                    dx, dy = p.x() - pos.x(), p.y() - pos.y()
                    if dx * dx + dy * dy <= tol2:
                        new_focused_pt = pt
                        break
                break

        # --- hover ---
        if new_hovered is not self.hovered_curve:
            if self.hovered_curve is not None:
                self.hovered_curve.set_hovered(False)
                self.hovered_curve.set_focused(False)  # also drop old focus
            self.hovered_curve = new_hovered
            if new_hovered is not None:
                new_hovered.set_hovered(True)

        # --- point focus ---
        if new_focused_pt is not self.focused_point:
            if self.focused_point is not None:
                self.focused_point.set_focused(False)
            self.focused_point = new_focused_pt
            if new_focused_pt is not None:
                new_focused_pt.set_focused(True)

        # --- curve focus ---
        # Cyan only when the cursor is on the stroke AND not on a point.
        if self.hovered_curve is not None:
            self.hovered_curve.set_focused(self.focused_point is None)

    def clear_hover(self):
        if self.hovered_curve is not None:
            self.hovered_curve.set_hovered(False)
            self.hovered_curve.set_focused(False)
            self.hovered_curve = None
        if self.focused_point is not None:
            self.focused_point.set_focused(False)
            self.focused_point = None

    # ------------------------------------------------------------
    #  Shape selection
    # ------------------------------------------------------------

    def set_selected_point(self, point):
        """Replace the whole selection with just `point` (or clear if None)."""
        if point is None:
            self.clear_selection()
            return
        if len(self.selected_points) == 1 and self.selected_points[0] is point:
            return
        self.clear_selection()
        self.selected_points.append(point)
        point.set_selected(True)

    def toggle_selection(self, point):
        if point in self.selected_points:
            self.selected_points.remove(point)
            point.set_selected(False)
        else:
            self.selected_points.append(point)
            point.set_selected(True)
        # Keep the curve's "fully selected" flag consistent with the point set.
        curve = point.curve
        curve.set_curve_selected(
            all(pt in self.selected_points for pt in curve.points))

    def clear_selection(self):
        for pt in self.selected_points:
            pt.set_selected(False)
            pt.curve.set_curve_selected(False)  # idempotent; harmless if not set
        self.selected_points.clear()
        self.shape_manager.select(None)

    def select_curve_under_hover(self, add: bool = False) -> bool:
        """Toggle selection of the hovered curve. With `add`, the curve joins
        the existing selection instead of replacing it. Returns True if handled."""
        if self.hovered_curve is None:
            return False
        curve = self.hovered_curve
        in_selection = all(pt in self.selected_points for pt in curve.points)

        if add:
            # Toggle membership; leave the rest of the selection alone.
            if in_selection:
                for pt in curve.points:
                    if pt in self.selected_points:
                        self.selected_points.remove(pt)
                        pt.set_selected(False)
                curve.set_curve_selected(False)
                self.messageLogged.emit(f"{curve.name} removed from selection")
            else:
                curve.set_curve_selected(True)
                for pt in curve.points:
                    if pt not in self.selected_points:
                        self.selected_points.append(pt)
                    pt.set_selected(True)
                self.messageLogged.emit(f"Added {curve.name} to selection")
            return True

        # No shift: replace, unless this curve is already the whole selection.
        if in_selection and len(self.selected_points) == len(curve.points):
            self.clear_selection()
            self.messageLogged.emit(f"{curve.name} deselected")
            return True
        self.clear_selection()
        curve.set_curve_selected(True)
        for pt in curve.points:
            self.selected_points.append(pt)
            pt.set_selected(True)
        self.messageLogged.emit(f"Selected {curve.name} ({len(curve.points)} points)")
        return True

    def set_curve_color(self, color):
        self.curve_color = QColor(color)
        for curve in self.curves:
            curve.set_color(self.curve_color)
        if self.pending_curve is not None:
            self.pending_curve.set_color(self.curve_color)
        self.shape_manager.apply_curve_colors()

    # ------------------------------------------------------------
    #  Curve finalization
    # ------------------------------------------------------------
    def finalize_curve(self):
        curve = self.pending_curve
        self.pending_curve = None
        curve.committed = True
        for pt in curve.points:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        curve.rebuild_path()
        self.curves.append(curve)
        self.selected_curve_idx = len(self.curves) - 1
        self.emit_svg()
        self.curveListChanged.emit()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Change notification from a curve
    # ------------------------------------------------------------
    def on_curve_changed(self):
        self.emit_svg()
        self.pointsChanged.emit()
        self.shape_manager.update_fills()

    # ------------------------------------------------------------
    #  Discard incomplete curve
    # ------------------------------------------------------------
    def discard_current_points(self):
        if self.pending_curve is None:
            return
        self.pending_curve.dispose()
        self.pending_curve = None
        self.emit_svg()
        self.pointsChanged.emit()
        self.messageLogged.emit("Incomplete curve discarded")

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        self.clear_hover()
        self.end_rotation(commit=False)
        self.set_selected_point(None)
        if self.pending_curve is not None:
            self.pending_curve.dispose()
            self.pending_curve = None

        # Pop each curve out of self.curves *before* disposing it, so
        # _refresh_shapes (triggered by unlink_point) never sees a curve
        # whose points list has already been emptied.
        while self.curves:
            self.curves.pop().dispose()
        self.curves.clear()  # harmless, keeps intent obvious
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selected_curve_idx = -1
        BezierCurve._next_id = 1 # c'est mieux de repartir à 1.
        self.dragging_point = None
        self._remove_background_image()
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()
        self.link_manager.reset()
        self.shape_manager.reset()

        self.messageLogged.emit("Scene cleared")

    # ------------------------------------------------------------
    #  Save and Load
    # ------------------------------------------------------------
    def generate_svg(self, bordered: bool = False):
        return scene_io.generate_svg(self, bordered=bordered)

    def emit_svg(self):
        # Preview mirrors the drawing area, so it always uses borders.
        self.svgCodeChanged.emit(scene_io.generate_svg(self, bordered=True))

    def save_state(self) -> dict:
        return scene_io.save_state(self)

    def load_state(self, state: dict):
        scene_io.load_state(self, state)

    # ------------------------------------------------------------
    #  Background image
    # ------------------------------------------------------------
    def load_background_image(self, filepath):
        pixmap = self._read_image(filepath)
        if pixmap is None:
            return False

        self._remove_background_image()
        self.background_image_path = filepath
        self.background_pixmap = pixmap

        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.35)
        item.setZValue(-50)  # above viewbox (-100), below curves (-1)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # click-through
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Scale to fit inside the viewbox, preserve aspect ratio, center it.
        vb = self.viewbox
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(vb.width() / pw, vb.height() / ph)
        item.setScale(scale)
        item.setPos(vb.center().x() - pw * scale / 2, vb.center().y() - ph * scale / 2)

        self.addItem(item)
        self.background_item = item
        self.messageLogged.emit(f"Background loaded: {filepath}")
        return True

    def _remove_background_image(self):
        if self.background_item is not None:
            self.removeItem(self.background_item)
            self.background_item = None
            self.background_image_path = None
            self.background_pixmap = None

    def _read_image(self, filepath):
        """Load a raster or SVG file into a QPixmap (or None on failure)."""
        if filepath.lower().endswith(".svg"):
            renderer = QSvgRenderer(filepath)
            if not renderer.isValid():
                return None

            # Determine intrinsic size: prefer the SVG's declared width/height,
            # fall back to the viewBox (which is what width/height usually mirror
            # anyway), and only as a true last resort use a square target.
            target = int(max(self.viewbox.width(), self.viewbox.height()) * 2)
            size = renderer.defaultSize()
            if size.isEmpty():
                size = renderer.viewBoxF().size().toSize()
            if size.isEmpty():
                size = QSize(target, target)

            # Scale up so the longest side matches `target`, preserving aspect ratio.
            scale = target / max(size.width(), size.height())
            size = QSize(int(size.width() * scale), int(size.height() * scale))

            image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            return QPixmap.fromImage(image)

        pixmap = QPixmap(filepath)
        return pixmap if not pixmap.isNull() else None

    # ------------------------------------------------------------
    #  Access to curves for info panel
    # ------------------------------------------------------------
    def get_curve_points(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            return self.curves[curve_idx].points
        return None

    def move_selected_points(self, dx: float, dy: float) -> bool:
        if not self.selected_points:
            return False
        offset = QPointF(dx, dy)
        for pt in self._with_linked(self.selected_points):
            pt.setPos(pt.pos() + offset)
        return True

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        if self.dragging_point is point:
            self.link_manager.update_proximity(point)

    def hide_hovered_curve_points(self) -> bool:
        if self.dragging_point is not None:
            return False  # don't hide a curve whose point is mid-drag
        if self.hovered_curve is None:
            return False
        self.hovered_curve.set_points_hidden(True)
        self.messageLogged.emit(f"Points hidden on {self.hovered_curve.name}")
        return True

    def show_all_points(self) -> int:
        n = 0
        for curve in self.curves:
            if curve.points_hidden:
                curve.set_points_hidden(False)
                n += 1
        if n:
            self.messageLogged.emit(f"Restored points on {n} curve(s)")
        return n

    # ------------------------------------------------------------
    #  Rotation
    # ------------------------------------------------------------
    def is_rotating(self) -> bool:
        return self._rotation_pivot is not None

    def _selected_curves(self) -> list[BezierCurve]:
        """Every curve currently part of the selection: the whole shape if
        one is selected, otherwise each curve flagged curve_selected."""
        shape = self.shape_manager.selected()
        if shape is not None:
            return list(shape.curves)
        return [c for c in self.curves if c.curve_selected]

    def _rotation_base_points(self) -> list[ControlPoint] | None:
        curves = self._selected_curves()
        if not curves:
            return None
        pts: set[ControlPoint] = set()
        for c in curves:
            pts.update(c.points)
        return list(pts)

    # ------------------------------------------------------------
    #  Mirror
    # ------------------------------------------------------------

    def mirror_selection(self, axis: str) -> bool:
        """Reflect the selection across the horizontal line (axis='x') or
        vertical line (axis='y') through the barycentre of its points."""
        if self.is_rotating():
            self.messageLogged.emit("Finish the rotation first")
            return False

        curves = self._selected_curves()
        if not curves:
            self.messageLogged.emit(
                "Nothing to mirror — select a curve (A or click) or a shape (S) first")
            return False

        base_pts: set[ControlPoint] = set()
        for c in curves:
            base_pts.update(c.points)
        px = sum(p.pos().x() for p in base_pts) / len(base_pts)
        py = sum(p.pos().y() for p in base_pts) / len(base_pts)

        # Include linked siblings so they stay coincident (same rule as rotation).
        targets = self._with_linked(base_pts)

        if axis == "x":
            # Reflect across the horizontal line y = py → flip y.
            for p in targets:
                pos = p.pos()
                p.setPos(pos.x(), 2 * py - pos.y())
        else:
            # Reflect across the vertical line x = px → flip x.
            for p in targets:
                pos = p.pos()
                p.setPos(2 * px - pos.x(), pos.y())

        self.messageLogged.emit(
            f"Mirrored across {axis.upper()} axis around ({px:.1f}, {py:.1f})")
        return True

    # ------------------------------------------------------------
    #  One-click curve presets
    # ------------------------------------------------------------
    def arm_preset(self, name: str) -> bool:
        """Arm a one-click preset. The next left-click in the canvas places
        it. Re-arming the same preset cancels it."""
        if name not in MOON_PRESETS:
            return False
        if self._preset_pending == name:
            self._preset_pending = None
            self.messageLogged.emit("Preset cancelled")
            return True
        if self.pending_curve is not None:
            self.messageLogged.emit("Finish or discard the current curve first")
            return False
        self._preset_pending = name
        self.messageLogged.emit(f"Click the canvas to place a '{name}' moon")
        return True

    def cancel_preset(self) -> bool:
        if self._preset_pending is None:
            return False
        self._preset_pending = None
        self.messageLogged.emit("Preset cancelled")
        return True

    def _place_preset(self, center: QPointF):
        name = self._preset_pending
        self._preset_pending = None
        curve = BezierCurve(self)
        for dx, dy in MOON_PRESETS[name]:
            curve.add_point(QPointF(center.x() + dx, center.y() + dy))
        # Route through finalize_curve so committed flags, signals, and the
        # curve list all get updated exactly like a normal curve.
        self.pending_curve = curve
        self.finalize_curve()
        self.messageLogged.emit(f"{curve.name} placed ({name} moon)")

    def start_rotation(self) -> bool:
        if self.is_rotating():
            return True
        base = self._rotation_base_points()
        if not base:
            self.messageLogged.emit(
                "Nothing to rotate — select a curve (A) or a shape (S) first")
            return False

        cx = sum(p.pos().x() for p in base) / len(base)
        cy = sum(p.pos().y() for p in base) / len(base)
        self._rotation_pivot = QPointF(cx, cy)

        # Include linked siblings so they stay coincident.
        targets = self._with_linked(base)

        self._rotation_starts = {p: p.pos() for p in targets}
        self._rotation_ref_angle = None  # captured on first mouse move

        self._show_pivot(cx, cy)
        self.rotationModeChanged.emit(True)
        self.messageLogged.emit(
            f"Rotating around ({cx:.1f}, {cy:.1f}) — right-click to validate, Esc to cancel")
        return True

    def end_rotation(self, commit: bool = True):
        if not self.is_rotating():
            return
        if not commit:
            for pt, start in self._rotation_starts.items():
                pt.setPos(start)
            self.on_curve_changed()  # one rebuild after restoring
        self._rotation_pivot = None
        self._rotation_ref_angle = None
        self._rotation_starts = {}
        self._hide_pivot()
        self.rotationModeChanged.emit(False)
        self.messageLogged.emit("Rotation validated" if commit else "Rotation cancelled")

    def _update_rotation(self, scene_pos: QPointF):
        if scene_pos is None or self._rotation_pivot is None:
            return
        px, py = self._rotation_pivot.x(), self._rotation_pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        if dx == 0.0 and dy == 0.0:
            return
        angle = math.atan2(dy, dx)
        if self._rotation_ref_angle is None:
            self._rotation_ref_angle = angle
            return
        delta = angle - self._rotation_ref_angle
        cos_a, sin_a = math.cos(delta), math.sin(delta)
        for pt, start in self._rotation_starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * cos_a - sy * sin_a,
                      py + sx * sin_a + sy * cos_a)

    def _show_pivot(self, x: float, y: float):
        r = ROTATION_PIVOT_RADIUS
        item = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        item.setBrush(QBrush(ROTATION_PIVOT_COLOR))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(1000)
        item.setPos(x, y)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(item)
        self._rotation_pivot_item = item

    def _hide_pivot(self):
        if self._rotation_pivot_item is not None:
            self.removeItem(self._rotation_pivot_item)
            self._rotation_pivot_item = None

