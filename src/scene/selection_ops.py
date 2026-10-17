# scene/selection_ops.py
"""SelectionOps: selection-driven actions on the scene.

State (points, shapes, hovered_curve, focused_point) lives in Selection.
This module holds the one-shot actions that *read* that state and act on
the scene through it: hit-testing under the cursor, rect selection,
select-all, chain/shape resolution from a hover, the save-shape payload.
It also holds the discrete edit operations that take their target from
the current selection (move, mirror, centre, snap, hide, delete).

None of these track state between calls.
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
        if n:
            scene.undo.push("Snap to grid")
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

        if axis == "x":
            if all(abs(p.pos().y() - py) < 1e-6 for p in base_pts):
                scene.messageLogged.emit("Nothing to mirror — selection is on the axis")
                return True
        else:
            if all(abs(p.pos().x() - px) < 1e-6 for p in base_pts):
                scene.messageLogged.emit("Nothing to mirror — selection is on the axis")
                return True

        scene.messageLogged.emit(
            f"Mirrored across {axis.upper()} axis around ({px:.1f}, {py:.1f})")
        if scene.transform.is_transforming():
            scene.transform.reanchor_transform()
        scene.undo.push(f"Mirror {axis.upper()}")
        return True

    def center_selection(self, axis: str) -> bool:
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

        if abs(offset) < 1e-6:
            scene.messageLogged.emit(f"Already centred {'horizontally' if axis == 'horizontal' else 'vertically'}")
            return True

        if scene.transform.is_transforming():
            scene.transform.reanchor_transform()
        scene.undo.push(f"Center {axis}")
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
        scene = self.scene
        if scene.dragging_point is not None:
            return False

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
            scene.undo.push(f"Hide points ({n})")
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
            scene.undo.push(f"Show all points ({n})")
        return n

    # ------------------------------------------------------------
    #  Delete
    # ------------------------------------------------------------
    def delete_selection(self) -> int:
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
        scene.undo.push(f"Delete ({n})")
        return n

    # ------------------------------------------------------------
    #  Hover-driven selection (A and S keys)
    # ------------------------------------------------------------
    def select_curve_under_hover(self, add: bool = False) -> bool:
        """Toggle selection of the hovered curve. With `add`, the curve joins
        the existing selection instead of replacing it. Returns True if handled."""
        scene = self.scene
        curve = scene.hovered_curve
        if curve is None:
            return False
        sel = scene.selection
        in_selection = sel.is_curve_selected(curve)

        if add:
            if in_selection:
                sel.remove_points(curve.points)
                scene.messageLogged.emit(f"{curve.name} removed from selection")
            else:
                sel.add_points(curve.points)
                scene.messageLogged.emit(f"Added {curve.name} to selection")
            return True

        if in_selection and len(sel.points) == len(curve.points):
            sel.clear()
            scene.messageLogged.emit(f"{curve.name} deselected")
            return True
        sel.clear()
        sel.add_points(curve.points)
        scene.messageLogged.emit(f"Selected {curve.name} ({len(curve.points)} points)")
        return True

    def select_shape_from_hover(self, add: bool = False) -> bool:
        """S key: select the hovered curve's shape (or its chain if the
        curve is not part of a closed loop)."""
        scene = self.scene
        hovered = scene.hovered_curve
        if hovered is None:
            return False

        shape = scene.shape_manager.shape_of_curve(hovered)
        if shape is not None:
            return self._select_single_shape(shape, add)

        chain = scene.shape_manager.chain_of(hovered)
        if len(chain) < 2:
            scene.messageLogged.emit(f"{hovered.name} is not linked to anything")
            return False
        return self._select_chain(chain, add)

    def _select_single_shape(self, shape, add: bool) -> bool:
        scene = self.scene
        sel = scene.selection
        if add:
            if sel.is_shape_selected(shape):
                sel.deselect_shape(shape)
                scene.messageLogged.emit(f"{shape.name} removed from selection")
            else:
                sel.select_shape(shape, add=True)
                scene.messageLogged.emit(f"Added {shape.name} to selection")
            return True

        any_curve_selected = any(c.curve_selected for c in scene.curves)
        sole_selection = (sel.shapes == {shape} and not any_curve_selected)

        sel.clear()
        if sole_selection:
            scene.messageLogged.emit(f"{shape.name} deselected")
        else:
            sel.select_shape(shape, add=False)
            scene.messageLogged.emit(f"{shape.name} selected")
        return True

    def _select_chain(self, chain, add: bool) -> bool:
        scene = self.scene
        sel = scene.selection
        chain_pts = [pt for c in chain for pt in c.points]
        if add:
            if all(sel.is_curve_selected(c) for c in chain):
                sel.remove_points(chain_pts)
                scene.messageLogged.emit("Chain removed from selection")
            else:
                sel.add_points(chain_pts)
                scene.messageLogged.emit(f"Added chain of {len(chain)} curves")
        else:
            sel.clear()
            sel.add_points(chain_pts)
            scene.messageLogged.emit(f"Selected chain of {len(chain)} curves")
        return True

    # ------------------------------------------------------------
    #  Rect selection (rubber band)
    # ------------------------------------------------------------
    def select_in_rect(self, rect, add: bool = False) -> int:
        """Select every visible control point whose position lies inside
        `rect` (scene coordinates). With `add`, keeps the existing selection."""
        scene = self.scene
        sel = scene.selection
        if not add:
            sel.clear()
        selected = sel.points
        to_add = []
        for curve in scene.curves:
            if curve.points_hidden:
                continue
            for pt in curve.points:
                if pt in selected:
                    continue
                if rect.contains(pt.model_pos()):
                    to_add.append(pt)
        sel.add_points(to_add)
        if to_add:
            scene.messageLogged.emit(f"Selected {len(to_add)} point(s)")
        return len(to_add)

    # ------------------------------------------------------------
    #  Select all
    # ------------------------------------------------------------
    def toggle_select_all(self) -> bool:
        """Ctrl+A: select every point on every visible curve, or clear the
        selection if every one of them is already selected."""
        scene = self.scene
        sel = scene.selection
        all_points = [pt for c in scene.curves
                      if not c.points_hidden
                      for pt in c.points]
        if not all_points:
            return False

        if all(pt in sel.points for pt in all_points):
            sel.clear()
            scene.messageLogged.emit("Selection cleared")
        else:
            sel.clear()
            sel.add_points(all_points)
            scene.messageLogged.emit(f"Selected {len(all_points)} point(s)")
        return True

    # ------------------------------------------------------------
    #  Save-shape payload
    # ------------------------------------------------------------
    def exportable_selection(self):
        """Return (kind, curves) for the Save Shape action, or (None, None).

        Accepts exactly one of: a shape, a chain, or a single curve.
        kind is "shape" / "chain" / "curve"; curves are UI BezierCurve objects
        in the order they should be saved.
        """
        scene = self.scene
        sel = scene.selection

        shapes = sel.shapes_in_selection()
        if len(shapes) > 1:
            return None, None
        if len(shapes) == 1:
            return "shape", scene.ui_curves(shapes[0])

        selected = [c for c in scene.curves if c.curve_selected]
        if not selected:
            return None, None
        if len(selected) == 1:
            return "curve", selected

        ids = frozenset(c.id for c in selected)
        for chain in scene.document.chains:
            if frozenset(c.id for c in chain.curves) == ids:
                ordered = [scene.registry.ui_curve_for(mc) for mc in chain.curves
                           if scene.registry.ui_curve_for(mc) is not None]
                return "chain", ordered
        return None, None