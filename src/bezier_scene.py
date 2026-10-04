# bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem
from PySide6.QtSvg import QSvgRenderer

from settings import (ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, SVG_FILL,
                      VIEWBOX_BORDER_WIDTH, LINK_PROXIMITY_TOLERANCE, SVG_STROKE_COLOR, SVG_STROKE_WIDTH)

from link_indicator import LinkIndicator
from control_point import ControlPoint
from bezier_curve import BezierCurve
import scene_io
from shape import Shape

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()
    curveListChanged = Signal()
    curveSelected = Signal(int)
    curveDragFinished = Signal()
    messageLogged = Signal(str)

    def __init__(self):
        super().__init__()

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT   # full working area (scene rect)
        self.viewbox = VIEWBOX_RECT     # region that gets exported

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        self.pending_curve = None     # BezierCurve currently being placed
        self.mode = "create"
        self.link_groups: list[list[ControlPoint]] = []
        self.curves = []
        self.shapes: list[Shape] = []
        self._propagating_links = False
        self.selected_curve_idx = -1
        self.dragging_point = None
        self._hovered_curve = None
        self._ensuring_visible = False
        self.background_item = None
        self.background_image_path = None
        self._proximity_target = None
        self.selected_points: list[ControlPoint] = []
        self._drag_targets: dict[ControlPoint, QPointF] = {}
        self._drag_primary_start: QPointF | None = None
        self._selected_shape = None

        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)

        self.link_indicator = LinkIndicator()
        self.addItem(self.link_indicator)

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        views = self.views()
        if not views:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.scenePos(), views[0].transform())

        if isinstance(item, ControlPoint) and item.curve.committed:
            # --- Existing committed-point logic, unchanged ---
            curve = item.curve
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if shift:
                self.toggle_selection(item)
                self._clear_hover()
                event.accept()
                return

            # Non-shift: if the clicked point isn't already in the selection, start fresh.
            if item not in self.selected_points:
                self.set_selected_point(item)

            self._clear_hover()
            self.dragging_point = item
            self._start_drag(item)
            curve.set_highlighted(True)
            idx = self.curves.index(curve)
            if idx != self.selected_curve_idx:
                self.selected_curve_idx = idx
                self.curveSelected.emit(idx)
            super().mousePressEvent(event)
            return

        # Not a committed control point → drop any previous selection.
        self.set_selected_point(None)

        if isinstance(item, ControlPoint):
            # Pending-curve point (create mode). Let Qt handle it, but don't
            # fall through to the create branch.
            super().mousePressEvent(event)
            return

        if self.mode == "create":
            if self.pending_curve is None:
                self.pending_curve = BezierCurve(self)

            self.pending_curve.add_point(event.scenePos())
            if self.pending_curve.is_complete():
                self.finalize_curve()
                self.messageLogged.emit(f"Curve created")
            return

        super().mousePressEvent(event)

    def _start_drag(self, primary):
        """Snapshot positions of every point that should follow this drag."""
        primary_group = set(self._group_of(primary) or [])
        primary_group.add(primary)

        # Seeds: all selected points + the primary (in case primary wasn't selected).
        seeds = set(self.selected_points)
        seeds.add(primary)

        # Expand to link-group siblings.
        targets = set()
        for pt in seeds:
            targets.add(pt)
            group = self._group_of(pt)
            if group:
                targets.update(group)

        # Primary and its group are moved by Qt + propagate_point_move — skip them.
        targets -= primary_group

        self._drag_targets = {pt: pt.pos() for pt in targets}
        self._drag_primary_start = primary.pos()


    def _group_of(self, point):
        """Return the link group containing `point`, or None."""
        for group in self.link_groups:
            for pt in group:
                if pt is point:
                    return group
        return None

    # ------------------------------------------------------------
    #  Shape detection
    # ------------------------------------------------------------

    # ------------------------------------------------------------
    #  Shape detection
    # ------------------------------------------------------------
    def _pair_partner(self, pt):
        """If `pt` is a curve endpoint whose link group is exactly {pt, other}
        and `other` is also an endpoint, return `other`. Otherwise None."""
        if pt.point_idx not in (0, 3):
            return None
        g = self._group_of(pt)
        if g is None or len(g) != 2:
            return None
        other = g[0] if g[1] is pt else g[1]
        if other.point_idx not in (0, 3):
            return None
        return other

    def _trace_loop_from(self, start_pt):
        """Walk from `start_pt` through link partners. Return the frozenset of
        curves if the walk returns to `start_pt`; otherwise None."""
        if self._pair_partner(start_pt) is None:
            return None
        current_pt = start_pt
        visited = []
        while True:
            partner = self._pair_partner(current_pt)
            if partner is None:
                return None  # dead end
            next_curve = partner.curve
            if next_curve in visited:
                return None  # revisited without closing
            visited.append(next_curve)
            # Advance to the far endpoint of next_curve
            other = (next_curve.points[3] if partner is next_curve.points[0]
                     else next_curve.points[0])
            if other is start_pt:
                return frozenset(visited)  # closed
            current_pt = other

    def _refresh_shapes(self):
        """Rebuild self.shapes from the current link topology. Existing Shape
        objects (and their names) are reused when the loop is unchanged.
        Emits 'formed' / 'dissolved' messages for the diff."""
        found = []
        seen = set()
        for curve in self.curves:
            if len(curve.points) < 4:  # curve is being disposed
                continue
            for idx in (0, 3):
                loop = self._trace_loop_from(curve.points[idx])
                if loop and loop not in seen:
                    seen.add(loop)
                    found.append(loop)

        existing = {shape.curves: shape for shape in self.shapes}
        new_shapes = []
        for curves in found:
            if curves in existing:
                new_shapes.append(existing[curves])
            else:
                shape = Shape(curves)
                new_shapes.append(shape)
                names = " + ".join(c.name for c in sorted(curves, key=lambda c: c.id))
                self.messageLogged.emit(f"{shape.name} formed from {names}")

        for shape in self.shapes:
            if shape not in new_shapes:
                self.messageLogged.emit(f"{shape.name} dissolved")

        self.shapes = new_shapes
        if self._selected_shape is not None and self._selected_shape not in new_shapes:
            self._selected_shape.set_selected(False)
            self.select_shape(None)

    def rebuild_shapes_from_links(self):
        """Reset shape state and re-detect all loops (used after loading)."""
        self.shapes.clear()
        Shape._next_id = 1
        self._refresh_shapes()



    def link_points(self, a, b):
        """Merge a's and b's link groups (creating one if needed)."""
        ga = self._group_of(a)
        gb = self._group_of(b)

        if ga is not None and ga is gb:
            return  # already linked

        if ga is None and gb is None:
            group = [a, b]
            self.link_groups.append(group)
        elif ga is None:
            gb.append(a)
            group = gb
        elif gb is None:
            ga.append(b)
            group = ga
        else:
            ga.extend(gb)
            self.link_groups.remove(gb)
            group = ga

        for pt in group:
            pt.set_linked(True)

        self._refresh_shapes()

    def unlink_point(self, point):
        """Remove `point` from its group."""
        for gi, group in enumerate(self.link_groups):
            for pi, pt in enumerate(group):
                if pt is point:
                    del group[pi]
                    if len(group) < 2:
                        for remaining in group:
                            remaining.set_linked(False)
                        del self.link_groups[gi]

                    self._refresh_shapes()
                    return

    def propagate_point_move(self, source, pos):
        """Move every other point in source's group to `pos`."""
        if self._propagating_links:
            return
        group = self._group_of(source)
        if group is None:
            return
        self._propagating_links = True
        try:
            for pt in group:
                if pt is not source:
                    pt.setPos(pos)
        finally:
            self._propagating_links = False

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
            self._update_proximity(self.dragging_point)

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
                self.dragging_point.curve.set_highlighted(False)
                self.dragging_point = None
                self._drag_targets = {}
                self._drag_primary_start = None
                self._clear_proximity()
                self._update_hover(event.scenePos())
                self.curveDragFinished.emit()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Hover tracking
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        """Called by the view's mouseMoved signal (scene_pos or None)."""
        if self.dragging_point is not None:
            return
        self._update_hover(scene_pos)

    def _update_hover(self, pos):
        new_hovered = None
        if pos is not None:
            for curve in reversed(self.curves):
                if curve.is_near(pos):
                    new_hovered = curve
                    break
        if new_hovered is self._hovered_curve:
            return
        if self._hovered_curve is not None:
            self._hovered_curve.set_hovered(False)
        self._hovered_curve = new_hovered
        if new_hovered is not None:
            new_hovered.set_hovered(True)

    def _clear_hover(self):
        if self._hovered_curve is not None:
            self._hovered_curve.set_hovered(False)
            self._hovered_curve = None

    # ------------------------------------------------------------
    #  Shape selection
    # ------------------------------------------------------------
    def select_shape(self, shape):
        """Set (or clear, with None) the currently selected shape."""
        if shape is self._selected_shape:
            return
        if self._selected_shape is not None:
            self._selected_shape.set_selected(False)
        self._selected_shape = shape
        if shape is not None:
            shape.set_selected(True)

    def shape_of_curve(self, curve):
        for shape in self.shapes:
            if curve in shape.curves:
                return shape
        return None

    def select_shape_from_hover(self):
        """Toggle selection of the shape containing the hovered curve.
        Returns True if handled (so the caller can accept the key event)."""
        if self._hovered_curve is None:
            return False
        shape = self.shape_of_curve(self._hovered_curve)
        if shape is None:
            self.messageLogged.emit(f"{self._hovered_curve.name} is not part of a shape")
            return False
        if shape is self._selected_shape:
            self.select_shape(None)
            self.messageLogged.emit(f"{shape.name} deselected")
        else:
            self.select_shape(shape)
            self.messageLogged.emit(f"{shape.name} selected")
        return True

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

    def clear_selection(self):
        for pt in self.selected_points:
            pt.set_selected(False)
        self.selected_points.clear()
        self.select_shape(None)


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

    # ------------------------------------------------------------
    #  SVG generation — viewBox is simply self.viewbox
    # ------------------------------------------------------------
    def generate_svg(self):
        path_commands = []
        for curve in self.curves:
            d = curve.svg_path_string()
            if d:
                path_commands.append(d)

        vb = self.viewbox
        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{vb.x():.2f} {vb.y():.2f} '
            f'{vb.width():.2f} {vb.height():.2f}" '
            f'width="{vb.width():.2f}" height="{vb.height():.2f}">'
        )

        if not path_commands:
            return header + '</svg>'

        d_string = " ".join(path_commands)
        return (
            header
            + f'<path d="{d_string}" fill="{SVG_FILL}" '
              f'stroke="{SVG_STROKE_COLOR}" '
              f'stroke-width="{SVG_STROKE_WIDTH}"/>'
              '</svg>'
        )

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
        self._clear_hover()
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

        self.selected_curve_idx = -1
        BezierCurve._next_id = 1 # c'est mieux de repartir à 1.
        self.dragging_point = None
        self._clear_proximity()
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()
        self._remove_background_image()
        self.link_groups.clear()
        self.select_shape(None)
        self.shapes.clear()
        Shape._next_id = 1
        self._propagating_links = False
        self.messageLogged.emit("Scene cleared")

    # ------------------------------------------------------------
    #  Save and Load
    # ------------------------------------------------------------
    def emit_svg(self):
        self.svgCodeChanged.emit(scene_io.generate_svg(self))

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
        item.setPos(vb.center().x() - pw * scale / 2,
                    vb.center().y() - ph * scale / 2)

        self.addItem(item)
        self.background_item = item
        print(f"scale = {scale}")
        self.messageLogged.emit(f"Background loaded: {filepath}")
        return True

    def _remove_background_image(self):
        if self.background_item is not None:
            self.removeItem(self.background_item)
            self.background_item = None
            self.background_image_path = None

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

    def move_selected_point(self, curve_idx, point_idx, pos):
        if 0 <= curve_idx < len(self.curves):
            self.curves[curve_idx].move_point(point_idx, pos)

    def move_selected_points(self, dx: float, dy: float) -> bool:
        if not self.selected_points:
            return False

        # Include link-group siblings so linked points stay coincident.
        to_move = set()
        for pt in self.selected_points:
            to_move.add(pt)
            group = self._group_of(pt)
            if group:
                to_move.update(group)

        offset = QPointF(dx, dy)
        for pt in to_move:
            pt.setPos(pt.pos() + offset)
        return True

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        if self.dragging_point is point:
            self._update_proximity(point)

    def _update_proximity(self, point):
        my_group = self._group_of(point)
        nearest = None
        best_d2 = LINK_PROXIMITY_TOLERANCE ** 2
        px, py = point.pos().x(), point.pos().y()

        for curve in self.curves:
            for other in curve.points:
                if other is point:
                    continue
                if my_group is not None and other in my_group:
                    continue
                ox, oy = other.pos().x(), other.pos().y()
                d2 = (ox - px) ** 2 + (oy - py) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    nearest = other

        if nearest is self._proximity_target:
            if nearest is not None:
                self.link_indicator.show_between(point.pos(), nearest.pos())
                print(f"[proximity] nearest={nearest is not None} target={self._proximity_target is not None}")
            return

        self._proximity_target = nearest
        if nearest is not None:
            self.link_indicator.show_between(point.pos(), nearest.pos())
        else:
            self.link_indicator.hide_indicator()

    def _clear_proximity(self):
        self._proximity_target = None
        self.link_indicator.hide_indicator()

    def try_link_proximity(self) -> bool:
        """Called when user presses 'L'. Links the dragged point to its neighbour."""
        print(f"[try_link] dragging={self.dragging_point} target={self._proximity_target}")
        if self.dragging_point is None or self._proximity_target is None:
            return False

        source = self.dragging_point
        target = self._proximity_target

        # Clear state *first* so the setPos below doesn't re-show the indicator.
        self._clear_proximity()

        # Link (so they'll move together from now on), then snap.
        self.link_points(source, target)
        source.setPos(target.pos())  # triggers rebuild + on_curve_changed
        self.messageLogged.emit(
            f"Linked {source.curve.name}·P{source.point_idx} "
            f"→ {target.curve.name}·P{target.point_idx}"
        )
        self.emit_svg()
        self.pointsChanged.emit()
        return True

    def hide_hovered_curve_points(self) -> bool:
        if self.dragging_point is not None:
            return False  # don't hide a curve whose point is mid-drag
        if self._hovered_curve is None:
            return False
        self._hovered_curve.set_points_hidden(True)
        self.messageLogged.emit(f"Points hidden on {self._hovered_curve.name}")
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