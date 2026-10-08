# bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter, QColor, QBrush
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsEllipseItem
from PySide6.QtSvg import QSvgRenderer

from settings import (ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH,
                      DEFAULT_CURVE_COLOR, ROTATION_PIVOT_RADIUS, ROTATION_PIVOT_COLOR, HOVER_TOLERANCE)

from presets import PRESETS
from link_manager import LinkManager
from control_point import ControlPoint
from bezier_curve import BezierCurve
import scene_io
import math
from shape_manager import ShapeManager
from new_data_model import Document, Point, Curve
from selection import Selection

SHAPE_FILL_Z = -10

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()
    curveListChanged = Signal()
    curveSelected = Signal(int)
    curveDragFinished = Signal()
    messageLogged = Signal(str)
    transformModeChanged = Signal(bool)
    presetStateChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.document = Document()
        self._curve_by_model: dict = {}
        self._model_by_curve: dict = {}
        self._pt_by_model: dict = {}
        self._model_by_pt: dict = {}

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT   # full working area (scene rect)
        self.viewbox = VIEWBOX_RECT     # region that gets exported

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        self.pending_curve = None     # BezierCurve currently being placed
        self.mode = "create"
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selection = Selection(self)

        self.selected_curve_idx = -1
        self.current_degree = 2
        self.dragging_point = None


        self._ensuring_visible = False
        self.background_item = None
        self.background_image_path = None
        self.background_pixmap = None
        self._preset_pending: str | None = None
        self._pending_collapse_point: ControlPoint | None = None
        self._drag_press_pos: QPointF | None = None
        self._transform_last_pos: QPointF | None = None
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

        self._transform_mode: str | None = None  # "rotate" | "scale" | None
        self._transform_pivot: QPointF | None = None
        self._transform_ref: float | None = None  # ref angle (rotate) or dist (scale)
        self._transform_starts: dict[ControlPoint, QPointF] = {}
        self._transform_pivot_item: QGraphicsEllipseItem | None = None

    @property
    def selected_points(self):
        return self.selection.points

    @property
    def hovered_curve(self):
        return self.selection.hovered_curve

    @property
    def focused_point(self):
        return self.selection.focused_point

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # A pending preset consumes this click, whatever the mode.
        if self._preset_pending is not None:
            keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self._place_preset(event.scenePos(), keep_armed=keep)
            return

        # ---- Create mode: left-click places a point, nothing else ----
        if self.mode == "create":
            if self.pending_curve is None:
                self.pending_curve = BezierCurve(self, degree=self.current_degree)
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
            # If the point is already part of a multi-point selection, defer
            # the collapse to release: a click collapses, a drag keeps the
            # whole selection and moves everything together.
            if item in self.selected_points and len(self.selected_points) > 1:
                self._pending_collapse_point = item
            else:
                self.set_selected_point(item)
                self._pending_collapse_point = None
            self._drag_press_pos = event.scenePos()

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

    def set_degree(self, degree: int):
        if degree not in (2, 3) or degree == self.current_degree:
            return
        self.current_degree = degree
        if self.pending_curve is not None:
            self.discard_current_points()
        self.messageLogged.emit(f"Curve type → {'quadratic' if degree == 2 else 'cubic'}")

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

        if self._pending_collapse_point is not None and self._drag_press_pos is not None:
            press = self._drag_press_pos
            cur = event.scenePos()
            dx, dy = cur.x() - press.x(), cur.y() - press.y()
            if dx * dx + dy * dy > 25:  # ~5 px — real movement, not jitter
                self._pending_collapse_point = None

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
                pending = self._pending_collapse_point
                self._pending_collapse_point = None
                self._drag_press_pos = None
                self.dragging_point = None
                self._drag_targets = {}
                self._drag_primary_start = None
                self.link_manager.clear_proximity()

                if pending is not None:
                    # No movement: it was a click. Collapse now.
                    self.set_selected_point(pending)

                self._update_hover(event.scenePos())
                self.curveDragFinished.emit()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Hover tracking
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        if self.is_transforming():
            if self.is_rotating():
                self._update_rotation(scene_pos)
            else:
                self._update_scaling(scene_pos)
            return
        if self.dragging_point is not None:
            return
        if self.mode == "create":
            return
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

        # Only the stroke counts as a curve hover — when a point is under
        # the cursor, focus moves to that point and the curve does not
        # count as hovered.
        if new_focused_pt is not None:
            new_hovered = None

        self.selection.set_hover(new_hovered, new_focused_pt)

    def clear_hover(self):
        self.selection.clear_hover()

    # ------------------------------------------------------------
    #  Shape selection
    # ------------------------------------------------------------
    def set_selected_point(self, point):
        """Replace the whole selection with just `point` (or clear if None)."""
        if point is None:
            self.clear_selection()
            return
        if len(self.selection.points) == 1 and self.selection.points[0] is point:
            return
        self.clear_selection()
        self.selection.set_point(point)

    def toggle_selection(self, point):
        self.selection.toggle_point(point)

    def clear_selection(self):
        self.selection.clear_points()
        self.shape_manager.select(None)

    def _propagate_move(self, source, pos):
        """Apply `pos` to every other point in source's link group.
        Base implementation reads from LinkManager directly."""
        group = self.link_manager.group_of(source)
        if group is None:
            return
        for pt in group:
            if pt is not source:
                pt.setPos(pos)

    def select_curve_under_hover(self, add: bool = False) -> bool:
        if self.hovered_curve is None:
            return False
        curve = self.hovered_curve
        sel = self.selection
        in_selection = sel.is_curve_selected(curve)

        if add:
            if in_selection:
                for pt in curve.points:
                    if pt in sel.points:
                        sel.points.remove(pt)
                        pt.update()
                curve.update()
                self.messageLogged.emit(f"{curve.name} removed from selection")
            else:
                for pt in curve.points:
                    if pt not in sel.points:
                        sel.points.append(pt)
                    pt.update()
                curve.update()
                self.messageLogged.emit(f"Added {curve.name} to selection")
            return True

        if in_selection and len(sel.points) == len(curve.points):
            self.clear_selection()
            self.messageLogged.emit(f"{curve.name} deselected")
            return True
        self.clear_selection()
        for pt in curve.points:
            sel.points.append(pt)
            pt.update()
        curve.update()
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
        self.end_transform(commit=False)
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
        #  Mirror
        # ------------------------------------------------------------

    def mirror_selection(self, axis: str) -> bool:
        """Reflect the selection across the horizontal line (axis='x') or
        vertical line (axis='y') through the barycentre of its points."""
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

        # Snapshot before moving: setPos on a linked point propagates to its
        # sibling, so reading pos() inside the loop would read already-moved
        # values. Compute every target from the pre-mirror positions.
        starts = {p: p.pos() for p in targets}
        if axis == "x":
            for p, start in starts.items():
                p.setPos(start.x(), 2 * py - start.y())
        else:
            for p, start in starts.items():
                p.setPos(2 * px - start.x(), start.y())

        self.messageLogged.emit(
            f"Mirrored across {axis.upper()} axis around ({px:.1f}, {py:.1f})")
        if self.is_transforming():
            self._reanchor_transform()
        return True

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
        targets = self._with_linked(self.selected_points)
        starts = {p: p.pos() for p in targets}
        for p, start in starts.items():
            p.setPos(start + offset)
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
    #  One-click presets
    # ------------------------------------------------------------
    def arm_preset(self, name: str) -> bool:
        if name not in PRESETS:
            return False
        if self._preset_pending == name:
            self._preset_pending = None
            self.presetStateChanged.emit("")
            self.messageLogged.emit("Preset cancelled")
            return True
        if self.pending_curve is not None:
            # Refused: sync the panel back to whatever state we're actually in.
            self.presetStateChanged.emit(self._preset_pending or "")
            self.messageLogged.emit("Finish or discard the current curve first")
            return False
        self._preset_pending = name
        self.presetStateChanged.emit(name)
        self.messageLogged.emit(
            f"Click the canvas to place '{PRESETS[name].label}'")
        return True

    def _place_preset(self, center: QPointF, keep_armed: bool = False):
        name = self._preset_pending
        if not keep_armed:
            self._preset_pending = None
            self.presetStateChanged.emit("")

        preset = PRESETS[name]
        degree = self.current_degree
        curves = []
        for cdef in preset.curves:
            curve = BezierCurve(self, degree=degree)
            for dx, dy in cdef.offsets_for_degree(degree):
                curve.add_point(QPointF(center.x() + dx, center.y() + dy))
            self.pending_curve = curve
            self.finalize_curve()
            curves.append(curve)

        for (ci, pi), (cj, pj) in preset.links:
            self.link_manager.link_points(curves[ci].points[pi], curves[cj].points[pj])

        kind = "cubic" if degree == 3 else "quadratic"
        if keep_armed:
            self.messageLogged.emit(
                f"{preset.label} placed ({kind}) — still armed, release Shift to stop")
        else:
            self.messageLogged.emit(f"{preset.label} placed ({kind})")

    def cancel_preset(self) -> bool:
        if self._preset_pending is None:
            return False
        self._preset_pending = None
        self.presetStateChanged.emit("")
        self.messageLogged.emit("Preset cancelled")
        return True

    def delete_selection(self) -> int:
        """Delete every curve selected directly (curve_selected) or via a
        selected shape. Returns the number of curves removed."""
        to_delete: set[BezierCurve] = set()
        for curve in self.curves:
            if curve.curve_selected:
                to_delete.add(curve)
        for shape in self.shape_manager.selected_shapes():
            to_delete.update(shape.curves)

        if not to_delete:
            self.messageLogged.emit("Nothing selected to delete")
            return 0

        self.clear_hover()

        # Clear shape selection first: this also drops the shapes' points
        # from selected_points, so the loop below only has to worry about
        # points selected via curve_selected.
        self.shape_manager.select(None)

        curves = list(to_delete)
        for curve in curves:
            self.curves.remove(curve)
            for pt in curve.points:
                if pt in self.selected_points:
                    self.selected_points.remove(pt)
                pt.update()

        # dispose() unlinks each point, which triggers shape_manager.refresh()
        # — any closed loop that used one of these curves dissolves naturally.
        for curve in curves:
            curve.dispose()

        self.selected_curve_idx = -1
        self.shape_manager.refresh()  # belt & braces; dispose already ran it
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()
        n = len(curves)
        self.messageLogged.emit(
            f"Deleted {curves[0].name}" if n == 1 else f"Deleted {n} curves")
        return n

    # ------------------------------------------------------------
    #  Transform: rotation and scaling share their machinery
    # ------------------------------------------------------------
    def is_rotating(self) -> bool:
        return self._transform_mode == "rotate"

    def is_scaling(self) -> bool:
        return self._transform_mode == "scale"

    def is_transforming(self) -> bool:
        return self._transform_mode is not None

    def _transform_base_points(self) -> set[ControlPoint] | None:
        """The points whose barycentre is the pivot: the selected shape's, or
        the selected curves'. None if nothing suitable is selected."""
        curves = self._selected_curves()
        if not curves:
            return None
        pts: set[ControlPoint] = set()
        for c in curves:
            pts.update(c.points)
        return pts

    def _selected_curves(self) -> list[BezierCurve]:
        """Every curve currently part of the selection — shape selection
        (S) and curve selection (A / click) are independent and both count."""
        curves: set[BezierCurve] = set()
        for shape in self.shape_manager.selected_shapes():
            curves.update(shape.curves)
        for c in self.curves:
            if c.curve_selected:
                curves.add(c)
        return list(curves)

    def _start_transform(self, mode: str) -> bool:
        if self.is_transforming():
            return True
        base = self._transform_base_points()
        if not base:
            self.messageLogged.emit(
                "Nothing to transform — select a curve (A or click) or a shape (S) first")
            return False

        cx = sum(p.pos().x() for p in base) / len(base)
        cy = sum(p.pos().y() for p in base) / len(base)

        self._transform_mode = mode
        self._transform_pivot = QPointF(cx, cy)
        self._transform_ref = None  # captured on first move
        self._transform_starts = {
            p: p.pos() for p in self._with_linked(base)}

        self._transform_last_pos = None
        self._show_pivot(cx, cy)
        self.transformModeChanged.emit(True)
        verb = "Rotating" if mode == "rotate" else "Scaling"
        self.messageLogged.emit(
            f"{verb} around ({cx:.1f}, {cy:.1f}) — right-click to validate, Esc to cancel")
        return True

    def _end_transform(self, commit: bool = True):
        if not self.is_transforming():
            return
        mode = self._transform_mode
        if not commit:
            for pt, start in self._transform_starts.items():
                pt.setPos(start)
            self.on_curve_changed()  # one rebuild after restoring
        self._transform_mode = None
        self._transform_pivot = None
        self._transform_ref = None
        self._transform_starts = {}
        self._hide_pivot()
        self.transformModeChanged.emit(False)
        verb = "Rotation" if mode == "rotate" else "Scaling"
        self.messageLogged.emit(f"{verb} validated" if commit else f"{verb} cancelled")

    def start_rotation(self) -> bool:
        return self._start_transform("rotate")

    def start_scaling(self) -> bool:
        return self._start_transform("scale")

    def end_transform(self, commit: bool = True):
        self._end_transform(commit)

    def _reanchor_transform(self):
        """After an external change to positions (e.g. a mirror during an
        active transform), realign the snapshot so the next update continues
        from the current positions instead of the pre-transform ones."""
        if self._transform_pivot is None:
            return
        for p in self._transform_starts:
            self._transform_starts[p] = p.pos()
        last = self._transform_last_pos
        if last is None:
            # No mouse move yet; let the first move capture a fresh reference.
            self._transform_ref = None
            return
        px = self._transform_pivot.x()
        py = self._transform_pivot.y()
        dx, dy = last.x() - px, last.y() - py
        if self.is_rotating():
            self._transform_ref = math.atan2(dy, dx) if (dx or dy) else None
        else:
            dist = math.hypot(dx, dy)
            self._transform_ref = dist if dist > 1e-6 else None

    def _update_rotation(self, scene_pos: QPointF):
        if scene_pos is None or self._transform_pivot is None:
            return
        self._transform_last_pos = QPointF(scene_pos)
        px, py = self._transform_pivot.x(), self._transform_pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        if dx == 0.0 and dy == 0.0:
            return
        angle = math.atan2(dy, dx)
        if self._transform_ref is None:
            self._transform_ref = angle
            return
        delta = angle - self._transform_ref
        cos_a, sin_a = math.cos(delta), math.sin(delta)
        for pt, start in self._transform_starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * cos_a - sy * sin_a,
                      py + sx * sin_a + sy * cos_a)

    def _update_scaling(self, scene_pos: QPointF):
        if scene_pos is None or self._transform_pivot is None:
            return
        self._transform_last_pos = QPointF(scene_pos)
        px, py = self._transform_pivot.x(), self._transform_pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return
        if self._transform_ref is None:
            self._transform_ref = dist
            return
        ratio = dist / self._transform_ref
        ratio = max(0.05, min(ratio, 50.0))  # guard against collapse/explosion
        for pt, start in self._transform_starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * ratio, py + sy * ratio)

    def _show_pivot(self, x: float, y: float):
        r = ROTATION_PIVOT_RADIUS
        item = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        item.setBrush(QBrush(ROTATION_PIVOT_COLOR))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(1000)
        item.setPos(x, y)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(item)
        self._transform_pivot_item = item

    def _hide_pivot(self):
        if self._transform_pivot_item is not None:
            self.removeItem(self._transform_pivot_item)
            self._transform_pivot_item = None


    def on_shift_released(self):
        """Releasing shift after shift-click placement unarms the preset."""
        if self._preset_pending is not None:
            self.cancel_preset()

    def _sync_model_registry(self):
        """Sync the model with the scene's current items. Additive: model
        Curve/Point objects persist across calls so identity is stable."""
        doc = self.document
        current = set(self.curves)

        # --- 1. Remove model curves whose UI items are gone. ---
        for curve_item in list(self._model_by_curve):
            if curve_item in current:
                continue
            mc = self._model_by_curve.pop(curve_item)
            self._curve_by_model.pop(mc, None)
            for mp in (*mc.extremities, *mc.controls):
                j = doc.junction_that_contains(mp)
                if j is not None:
                    doc.unlink(mp)
                item = self._pt_by_model.pop(mp, None)
                if item is not None:
                    self._model_by_pt.pop(item, None)
                if mp in doc.extremities:
                    doc.extremities.remove(mp)
                elif mp in doc.controls:
                    doc.controls.remove(mp)
            if mc in doc.curves:
                doc.curves.remove(mc)

        # --- 2. Add new curves / refresh positions on existing ones. ---
        for curve_item in self.curves:
            if not curve_item.is_complete():
                continue
            ui_pts = curve_item.points
            mc = self._model_by_curve.get(curve_item)
            if mc is None:
                mps = []
                for pt_item in ui_pts:
                    mp = Point(pt_item.pos().x(), pt_item.pos().y())
                    mps.append(mp)
                    self._pt_by_model[mp] = pt_item
                    self._model_by_pt[pt_item] = mp
                extremities = (mps[0], mps[-1])
                controls = mps[1:-1]
                mc = Curve(extremities, controls, curve_item.degree)
                mc.id = curve_item.id
                doc.curves.append(mc)
                doc.extremities.extend(extremities)
                doc.controls.extend(controls)
                self._model_by_curve[curve_item] = mc
                self._curve_by_model[mc] = curve_item