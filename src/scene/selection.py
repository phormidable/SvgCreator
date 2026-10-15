# scene/selection.py
"""Selection: authoritative selection state for the scene."""

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

    def is_curve_shape_selected(self, curve) -> bool:
        shape = self.scene.shape_manager.shape_of_curve(curve)
        return shape is not None and shape in self.shapes

    # def first_selected_shape(self):
    #     return next(iter(self.shapes), None)

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
    #  Shape mutations
    # ------------------------------------------------------------
    def select_shape(self, shape, add: bool = False):
        """Make `shape` the selected shape (add=True joins the selection).
        shape=None clears the shape selection. Mirrors the point-selection
        side of the API: keeps self.points in sync with shape membership."""
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
    #  Selection from hover (S key)
    # ------------------------------------------------------------
    def select_shape_from_hover(self, add: bool = False) -> bool:
        """S key: select the hovered curve's shape (or its chain if the
        curve is not part of a closed loop)."""
        hovered = self.scene.hovered_curve
        if hovered is None:
            return False

        shape = self.scene.shape_manager.shape_of_curve(hovered)
        if shape is not None:
            return self._select_single_shape(shape, add)

        chain = self.scene.shape_manager.chain_of(hovered)
        if len(chain) < 2:
            self.scene.messageLogged.emit(
                f"{hovered.name} is not linked to anything")
            return False
        return self._select_chain(chain, add)

    def _select_single_shape(self, shape, add: bool) -> bool:
        if add:
            if self.is_shape_selected(shape):
                self.deselect_shape(shape)
                self.scene.messageLogged.emit(
                    f"{shape.name} removed from selection")
            else:
                self.select_shape(shape, add=True)
                self.scene.messageLogged.emit(
                    f"Added {shape.name} to selection")
            return True

        # No shift: this shape becomes the whole selection — unless it
        # already was, in which case toggle it off.
        any_curve_selected = any(c.curve_selected for c in self.scene.curves)
        sole_selection = (self.shapes == {shape} and not any_curve_selected)

        self.scene.clear_selection()
        if sole_selection:
            self.scene.messageLogged.emit(f"{shape.name} deselected")
        else:
            self.select_shape(shape, add=False)
            self.scene.messageLogged.emit(f"{shape.name} selected")
        return True

    def _select_chain(self, chain, add: bool) -> bool:
        scene = self.scene
        chain_pts = [pt for c in chain for pt in c.points]
        if add:
            if all(self.is_curve_selected(c) for c in chain):
                self.remove_points(chain_pts)
                scene.messageLogged.emit("Chain removed from selection")
            else:
                self.add_points(chain_pts)
                scene.messageLogged.emit(f"Added chain of {len(chain)} curves")
            return True

        scene.clear_selection()
        self.add_points(chain_pts)
        scene.messageLogged.emit(f"Selected chain of {len(chain)} curves")
        return True

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

    def exportable_selection(self):
        """Return (kind, curves) for the Save Shape action, or (None, None).

        Accepts exactly one of: a shape, a chain, or a single curve.
        kind is "shape" / "chain" / "curve"; curves are UI BezierCurve objects
        in the order they should be saved.
        """
        scene = self.scene

        # 1) Exactly one shape (S-selected, or all its curves curve-selected).
        shapes = self.shapes_in_selection()
        if len(shapes) > 1:
            return None, None
        if len(shapes) == 1:
            return "shape", scene.ui_curves(shapes[0])

        # 2) Curves selected directly (via A / click).
        selected = [c for c in scene.curves if c.curve_selected]
        if not selected:
            return None, None
        if len(selected) == 1:
            return "curve", selected

        # 3) Several curves: they must form exactly one chain.
        ids = frozenset(c.id for c in selected)
        for chain in scene.document.chains:  # ← `chain` lives here
            if frozenset(c.id for c in chain.curves) == ids:
                ordered = [scene.registry.ui_curve_for(mc) for mc in chain.curves
                           if scene.registry.ui_curve_for(mc) is not None]
                return "chain", ordered
        return None, None

    # in Selection

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