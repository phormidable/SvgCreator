# scene/selection_ops.py
"""SelectionOps: discrete one-shot operations on the current selection.

These all share a shape — guard on an empty selection, read the current
selection, mutate the underlying points/curves, log a message, and
re-anchor a live transform if one is running. None of them track state
between calls, unlike TransformController, which drives an interactive
pivot-through-mouse gesture.

Reads through `self.scene`: selected_points, hovered_curve, focused_point,
dragging_point, curves, viewbox, link_manager, selection, shape_manager,
transform, grid_item, plus the messageLogged / hoveredPointChanged signals.
"""

from PySide6.QtCore import QPointF

from .curve_geometry import curve_bbox
from .items.bezier_curve import BezierCurve


class SelectionOps:
    def __init__(self, scene):
        self.scene = scene

    # ------------------------------------------------------------
    #  Move
    # ------------------------------------------------------------
    def move_selected_points(self, dx: float, dy: float) -> bool:
        scene = self.scene
        if not scene.selected_points:
            return False
        offset = QPointF(dx, dy)
        targets = scene.link_manager.with_linked(scene.selected_points)
        starts = {p: p.model_pos() for p in targets}
        for p, start in starts.items():
            p.setPos(start + offset)
        # The mouse hasn't moved and the hovered point is unchanged, so
        # nothing downstream refreshes the tooltip. Re-emit so it picks up
        # the new position.
        if scene.focused_point is not None:
            scene.hoveredPointChanged.emit(scene.focused_point)
        return True

    def snap_selection_to_grid(self) -> int:
        """Snap every selected point (plus its linked siblings) to the
        nearest grid line. Uses the current spacing regardless of the snap
        toggle — the caller has explicitly asked for it. Returns the number
        of points whose position actually changed."""
        scene = self.scene
        if not scene.selected_points:
            return 0
        targets = scene.link_manager.with_linked(scene.selected_points)
        n = 0
        for pt in targets:
            start = pt.model_pos()
            snapped = scene.grid_item.snap_to(start)
            if snapped != start:
                pt.setPos(snapped)
                n += 1
        return n

    # ------------------------------------------------------------
    #  Mirror / centre
    # ------------------------------------------------------------
    def mirror_selection(self, axis: str) -> bool:
        """Reflect the selection across the horizontal line (axis='x') or
        vertical line (axis='y') through the barycentre of its points."""
        scene = self.scene
        if not scene.selected_points:
            scene.messageLogged.emit(
                "Nothing to mirror — select a curve (A or click) or a shape (S) first")
            return False

        base_pts = set(scene.selected_points)
        px = sum(p.pos().x() for p in base_pts) / len(base_pts)
        py = sum(p.pos().y() for p in base_pts) / len(base_pts)

        # Include linked siblings so they stay coincident.
        targets = scene.link_manager.with_linked(base_pts)
        starts = {p: p.pos() for p in targets}
        if axis == "x":
            for p, start in starts.items():
                p.setPos(start.x(), 2 * py - start.y())
        else:
            for p, start in starts.items():
                p.setPos(2 * px - start.x(), start.y())

        scene.messageLogged.emit(
            f"Mirrored across {axis.upper()} axis around ({px:.1f}, {py:.1f})")
        if scene.transform.is_transforming():
            scene.transform.reanchor_transform()
        return True

    def center_selection(self, axis: str) -> bool:
        """Move the selection so its curve-bbox centre aligns with the
        viewbox centre along one axis.

        axis='horizontal': equal margins left/right (adjusts x).
        axis='vertical':   equal margins top/bottom (adjusts y).
        """
        scene = self.scene
        if not scene.selected_points:
            scene.messageLogged.emit(
                "Nothing to centre — select a curve (A or click) or a shape (S) first")
            return False

        bbox = self.selection_curve_bbox()
        if bbox is None:
            return False
        min_x, min_y, max_x, max_y = bbox

        targets = scene.link_manager.with_linked(set(scene.selected_points))
        starts = {p: p.pos() for p in targets}

        center = scene.viewbox.center()
        if axis == "horizontal":
            offset = center.x() - (min_x + max_x) / 2
            for p, start in starts.items():
                p.setPos(start.x() + offset, start.y())
            scene.messageLogged.emit(f"Centred horizontally on x={center.x():.1f}")
        elif axis == "vertical":
            offset = center.y() - (min_y + max_y) / 2
            for p, start in starts.items():
                p.setPos(start.x(), start.y() + offset)
            scene.messageLogged.emit(f"Centred vertically on y={center.y():.1f}")
        else:
            return False

        if scene.transform.is_transforming():
            scene.transform.reanchor_transform()
        return True

    def selection_curve_bbox(self):
        """Tight bbox (min_x, min_y, max_x, max_y) of the actual curve
        geometry for every curve touched by the selection. None if no curve
        is involved. Unlike a control-polygon bbox, this ignores handles that
        wander away from the curve."""
        curves = {pt.curve for pt in self.scene.selected_points
                  if pt.curve is not None}
        if not curves:
            return None

        boxes = []
        for curve in curves:
            pts = [(p.model_pos().x(), p.model_pos().y()) for p in curve.points]
            boxes.append(curve_bbox(pts, curve.degree))

        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))

    # ------------------------------------------------------------
    #  Visibility
    # ------------------------------------------------------------
    def hide_points(self) -> bool:
        """Hide the control points of every curve that has a point in the
        selection. Falls back to the hovered curve when nothing is selected."""
        scene = self.scene
        if scene.dragging_point is not None:
            return False  # don't yank points out from under an active drag

        curves = {pt.curve for pt in scene.selected_points if pt.curve is not None}
        if not curves and scene.hovered_curve is not None:
            curves = {scene.hovered_curve}
        if not curves:
            scene.messageLogged.emit(
                "Nothing to hide — hover a curve or select points first")
            return False

        n = sum(1 for c in curves if not c.points_hidden)
        for c in curves:
            c.set_points_hidden(True)
        if n:
            scene.messageLogged.emit(f"Points hidden on {n} curve(s)")
        return n > 0

    def show_all_points(self) -> int:
        scene = self.scene
        n = 0
        for curve in scene.curves:
            if curve.points_hidden:
                curve.set_points_hidden(False)
                n += 1
        if n:
            scene.messageLogged.emit(f"Restored points on {n} curve(s)")
        return n

    # ------------------------------------------------------------
    #  Delete
    # ------------------------------------------------------------
    def delete_selection(self) -> int:
        """Delete every curve selected directly (curve_selected) or via a
        selected shape. Returns the number of curves removed."""
        scene = self.scene
        to_delete: set[BezierCurve] = set()
        for curve in scene.curves:
            if curve.curve_selected:
                to_delete.add(curve)
        for shape in scene.selection.selected_shapes():
            to_delete.update(scene.ui_curves(shape))

        if not to_delete:
            scene.messageLogged.emit("Nothing selected to delete")
            return 0

        scene.clear_hover()
        scene.selection.select_shape(None)

        curves = list(to_delete)
        for curve in curves:
            scene.curves.remove(curve)
            for pt in curve.points:
                if pt in scene.selected_points:
                    scene.selected_points.remove(pt)
                pt.update()

        for curve in curves:
            curve.dispose()

        scene.shape_manager.refresh()
        scene.emit_svg()
        n = len(curves)
        scene.messageLogged.emit(
            f"Deleted {curves[0].name}" if n == 1 else f"Deleted {n} curves")
        return n