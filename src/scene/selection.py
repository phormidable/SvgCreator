# scene/selection.py
"""Selection: authoritative selection and hover state for the scene.

State only. Holds points, shapes, hovered_curve, focused_point, plus the
low-level mutations that keep `points` and `shapes` consistent with each
other (set_point, toggle_point, clear, add_points, select_shape,
set_hover, …). Actions that read from the scene to *decide* what to
select — hover-driven selection, rect selection, select-all, chain and
shape resolution, the save-shape payload — live in SelectionOps.
"""


class Selection:
    def __init__(self, scene):
        self.scene = scene
        self.points: list = []           # ControlPoint, in selection order
        self.shapes: set = set()         # UI Shape objects
        self.hovered_curve = None        # BezierCurve | None
        self.focused_point = None        # ControlPoint | None

    # ------------------------------------------------------------
    #  Queries
    # ------------------------------------------------------------
    def is_point_selected(self, pt) -> bool:
        return pt in self.points

    def is_curve_selected(self, curve) -> bool:
        """A curve is 'selected' when all of its points are in the
        selection. This is the rule the current code uses via the
        curve_selected flag on BezierCurve."""
        return bool(curve.points) and all(
            p in self.points for p in curve.points)

    def is_shape_selected(self, shape) -> bool:
        return shape in self.shapes

    def is_curve_shape_selected(self, curve) -> bool:
        shape = self.scene.shape_manager.shape_of_curve(curve)
        return shape is not None and shape in self.shapes

    def selected_shapes(self) -> list:
        return list(self.shapes)

    def shapes_in_selection(self) -> list:
        """Shapes that are effectively part of the selection: explicitly
        S-selected ones, plus any shape whose every curve is curve_selected."""
        result = set(self.shapes)
        flagged = {c for c in self.scene.curves if c.curve_selected}
        for shape in self.scene.shape_manager.shapes:
            if shape.curves and set(self.scene.ui_curves(shape)) <= flagged:
                result.add(shape)
        return list(result)

    # ------------------------------------------------------------
    #  Point mutations
    # ------------------------------------------------------------
    def set_point(self, pt):
        """Replace the whole selection (points AND shapes) with just `pt`
        (or clear everything if None)."""
        if pt is None:
            self.clear()
            return
        if len(self.points) == 1 and self.points[0] is pt:
            return
        self.clear()
        self.points.append(pt)
        pt.update()
        pt.curve.update()

    def clear(self):
        """Clear both point and shape selection."""
        self.clear_points()
        self.select_shape(None)

    def toggle_point(self, pt):
        if pt in self.points:
            self.points.remove(pt)
        else:
            self.points.append(pt)
        pt.update()
        pt.curve.update()

    def clear_points(self):
        affected = list(self.points)
        self.points.clear()
        for pt in affected:
            pt.update()
            pt.curve.update()

    def add_points(self, points):
        """Add every point not already in the selection and repaint them."""
        added = []
        for pt in points:
            if pt not in self.points:
                self.points.append(pt)
                added.append(pt)
        self._repaint(added)

    def remove_points(self, points):
        """Drop every point that is currently in the selection and repaint."""
        removed = []
        for pt in points:
            if pt in self.points:
                self.points.remove(pt)
                removed.append(pt)
        self._repaint(removed)

    @staticmethod
    def _repaint(points):
        """One update() per touched curve, not per point."""
        curves = set()
        for pt in points:
            pt.update()
            if pt.curve is not None:
                curves.add(pt.curve)
        for c in curves:
            c.update()

    # ------------------------------------------------------------
    #  Shape mutations
    # ------------------------------------------------------------
    def select_shape(self, shape, add: bool = False):
        """Make `shape` the selected shape (add=True joins the selection).
        shape=None clears the shape selection. Keeps self.points in sync
        with shape membership."""
        if shape is None:
            to_remove = list(self.shapes)
            self.clear_shapes()
            self._sync_shape_points(to_remove, add=False)
            return

        if add:
            if not self.is_shape_selected(shape):
                self.toggle_shape(shape)
                self._sync_shape_points([shape], add=True)
            return

        to_remove = [s for s in self.shapes if s is not shape]
        for s in to_remove:
            self.toggle_shape(s)
        if not self.is_shape_selected(shape):
            self.toggle_shape(shape)
            self._sync_shape_points([shape], add=True)
        if to_remove:
            self._sync_shape_points(to_remove, add=False)

    def toggle_shape(self, shape):
        if shape in self.shapes:
            self.shapes.discard(shape)
        else:
            self.shapes.add(shape)
        for curve in self.scene.ui_curves(shape):
            curve.update()

    def deselect_shape(self, shape):
        if self.is_shape_selected(shape):
            self.toggle_shape(shape)
            self._sync_shape_points([shape], add=False)

    def clear_shapes(self):
        for shape in self.shapes:
            for curve in self.scene.ui_curves(shape):
                curve.update()
        self.shapes.clear()

    def _sync_shape_points(self, shapes, add: bool):
        pts = [pt
               for shape in shapes
               for curve in self.scene.ui_curves(shape)
               for pt in curve.points]
        if add:
            self.add_points(pts)
        else:
            self.remove_points(pts)

    # ------------------------------------------------------------
    #  Hover
    # ------------------------------------------------------------
    def set_hover(self, curve, point):
        """Set the hovered curve and the focused point.

        The item flags are derived properties (see ControlPoint.hovered,
        BezierCurve.hovered, etc.), so we only need to update our own state
        and trigger repaints on the affected items.
        """
        affected = set()
        for c in (self.hovered_curve, curve):
            if c is not None:
                affected.add(c)
                affected.update(c.points)
        for p in (self.focused_point, point):
            if p is not None:
                affected.add(p)
                if p.curve is not None:
                    affected.add(p.curve)

        self.hovered_curve = curve
        self.focused_point = point

        for item in affected:
            item.update()

    def clear_hover(self):
        self.set_hover(None, None)