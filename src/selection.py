# selection.py
"""Selection: authoritative selection state for the scene.

Stage A: only the point selection. Shapes, hover, and focus will migrate
here in later stages. Until then, this object coexists with the older
selection state on the scene (hovered_curve, focused_point) and on
ShapeManager (_selected_shapes).

The methods here mutate the authoritative state and update the
corresponding UI flags. Callers use the properties on the items
(pt.selected, curve.curve_selected) to query, and the methods on this
object to change what's selected.
"""


class Selection:
    def __init__(self, scene):
        self.scene = scene
        self.points: list = []   # ControlPoint, in selection order
        self.shapes: set = set()   # UI Shape objects
        self.hovered_curve = None    # BezierCurve | None
        self.focused_point = None    # ControlPoint | None

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

    # ------------------------------------------------------------
    #  Point mutations
    # ------------------------------------------------------------
    def set_point(self, pt):
        self.clear_points()
        if pt is not None:
            self.points.append(pt)
            pt.update()
            pt.curve.update()

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

    # ------------------------------------------------------------
    #  Shape queries
    # ------------------------------------------------------------
    def is_shape_selected(self, shape) -> bool:
        return shape in self.shapes

    def first_selected_shape(self):
        return next(iter(self.shapes), None)

    def selected_shapes_list(self) -> list:
        return list(self.shapes)

    # ------------------------------------------------------------
    #  Shape mutations
    # ------------------------------------------------------------
    def set_shape(self, shape):
        """Make `shape` the sole selected shape. Use None to clear."""
        self.clear_shapes()
        if shape is not None:
            self.shapes.add(shape)
            shape.set_selected(True)

    def toggle_shape(self, shape):
        if shape in self.shapes:
            self.shapes.discard(shape)
            shape.set_selected(False)
        else:
            self.shapes.add(shape)
            shape.set_selected(True)

    def clear_shapes(self):
        for shape in self.shapes:
            shape.set_selected(False)
        self.shapes.clear()

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