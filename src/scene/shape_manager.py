# shape_manager.py
"""ShapeManager: owns the Shape objects (closed loops of one or more
curves), their fill rendering, and which one (if any) is selected.

A "loop" is a walk over curve endpoints through link groups. Each curve
contributes one cubic segment; the walk closes when it returns to its
starting endpoint.

Owned state: shapes, _selected.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem
from core.settings import SVG_PRECISION, SHAPE_BORDER_DARKEN, SHAPE_TRANSPARENT_OPACITY
from core.model import Shape

SHAPE_FILL_Z = -10

class ShapeManager:
    def __init__(self, scene):
        self.scene = scene
        self._transparent = False
        self._shaped_curves: set = set()  # curves whose opacity we last set
        self._last_opacity: float = 1.0  # value we last applied to those curves
        self._fills: dict = {}  # model Shape → QGraphicsPathItem

    @property
    def shapes(self):
        return self.scene.document.shapes

    # ------------------------------------------------------------
    #  Selection
    # ------------------------------------------------------------
    def selected(self) -> Shape | None:
        """First selected shape, or None. Convenience for single-selection UIs."""
        return self.scene.selection.first_selected_shape()

    def selected_shapes(self) -> list[Shape]:
        return self.scene.selection.selected_shapes_list()

    def shapes_in_selection(self) -> list[Shape]:
        """Shapes that are effectively part of the selection: explicitly
        S-selected ones, plus any shape whose every curve is curve_selected
        (e.g. reached via S on an open chain that includes the shape)."""
        result = set(self.scene.selection.shapes)
        flagged = {c for c in self.scene.curves if c.curve_selected}
        for shape in self.shapes:
            if shape.curves and set(self.scene.ui_curves(shape)) <= flagged:
                result.add(shape)
        return list(result)

    def _sync_curve_points_for_shapes(self, shapes, add: bool):
        pts = self.scene.selected_points
        for shape in shapes:
            for curve in self.scene.ui_curves(shape):
                for pt in curve.points:
                    if add:
                        if pt not in pts:
                            pts.append(pt)
                    else:
                        if pt in pts:
                            pts.remove(pt)
                    pt.update()
                curve.update()


    def select(self, shape: Shape | None, add: bool = False):
        sel = self.scene.selection
        if shape is None:
            to_remove = list(sel.shapes)
            sel.clear_shapes()
            self._sync_curve_points_for_shapes(to_remove, add=False)
            return
        if add:
            if not sel.is_shape_selected(shape):
                sel.toggle_shape(shape)
                self._sync_curve_points_for_shapes([shape], add=True)
            return
        to_remove = [s for s in sel.shapes if s is not shape]
        for s in to_remove:
            sel.toggle_shape(s)  # removes
        if not sel.is_shape_selected(shape):
            sel.toggle_shape(shape)
            self._sync_curve_points_for_shapes([shape], add=True)
        if to_remove:
            self._sync_curve_points_for_shapes(to_remove, add=False)

    def deselect(self, shape: Shape):
        if self.scene.selection.is_shape_selected(shape):
            self.scene.selection.toggle_shape(shape)
            self._sync_curve_points_for_shapes([shape], add=False)

    def set_transparent(self, value: bool):
        """Enable/disable transparent rendering of every shape."""
        if self._transparent == value:
            return
        self._transparent = value
        self._apply_transparency_to_all()

    def _apply_transparency_to_all(self):
        """Sync each curve's opacity with its shape membership, touching only
        curves whose target opacity actually changed since last call."""
        shaped: set = set()
        for shape in self.shapes:
            shaped.update(self.scene.ui_curves(shape))

        opacity = SHAPE_TRANSPARENT_OPACITY if self._transparent else 1.0
        prev_shaped = self._shaped_curves
        prev_opacity = self._last_opacity

        # Curves that joined a shape → fade to `opacity`.
        for curve in shaped - prev_shaped:
            self._set_curve_opacity(curve, opacity)
        # Curves that left a shape → back to solid.
        for curve in prev_shaped - shaped:
            self._set_curve_opacity(curve, 1.0)
        # Curves still in a shape, but the mode flipped → reapply.
        if opacity != prev_opacity:
            for curve in shaped & prev_shaped:
                self._set_curve_opacity(curve, opacity)

        self._shaped_curves = shaped
        self._last_opacity = opacity

        # Fill items: one per shape, keyed by the model Shape itself.
        for shape in self.shapes:
            item = self._fills.get(shape)
            if item is not None:
                item.setOpacity(opacity)

    @staticmethod
    def _set_curve_opacity(curve, opacity):
        curve.setOpacity(opacity)
        for pt in curve.points:
            pt.setOpacity(opacity)

    def shape_of_curve(self, curve):
        mcurve = self.scene.registry.model_curve_for(curve)
        if mcurve is None:
            return None
        for shape in self.shapes:
            if mcurve in shape.curves:
                return shape
        return None

    def select_from_hover(self, add: bool = False) -> bool:
        hovered = self.scene.hovered_curve
        if hovered is None:
            return False

        shape = self.shape_of_curve(hovered)
        if shape is not None:
            return self._select_shape(shape, add=add)

        # Not in a closed loop — try an open chain.
        chain = self.chain_of(hovered)
        if len(chain) < 2:
            self.scene.messageLogged.emit(
                f"{hovered.name} is not linked to anything")
            return False
        return self._select_chain(chain, add=add)

    def _select_shape(self, shape, add: bool) -> bool:
        if add:
            if self.scene.selection.is_shape_selected(shape):
                self.deselect(shape)
                self.scene.messageLogged.emit(
                    f"{shape.name} removed from selection")
            else:
                self.select(shape, add=True)
                self.scene.messageLogged.emit(
                    f"Added {shape.name} to selection")
            return True

        # No shift: this shape becomes the whole selection.
        # Toggle off only if it already was — i.e. no curve is also selected.
        any_curve_selected = any(c.curve_selected for c in self.scene.curves)
        sole_selection = (self.scene.selection.shapes == {shape}
                          and not any_curve_selected)

        self.scene.clear_selection()
        if sole_selection:
            self.scene.messageLogged.emit(f"{shape.name} deselected")
        else:
            self.select(shape, add=False)
            self.scene.messageLogged.emit(f"{shape.name} selected")
        return True

    def _select_chain(self, chain, add: bool) -> bool:
        scene = self.scene
        sel = scene.selection
        if add:
            if all(sel.is_curve_selected(c) for c in chain):
                for c in chain:
                    for pt in c.points:
                        if pt in sel.points:
                            sel.points.remove(pt)
                        pt.update()
                    c.update()
                scene.messageLogged.emit("Chain removed from selection")
            else:
                for c in chain:
                    for pt in c.points:
                        if pt not in sel.points:
                            sel.points.append(pt)
                        pt.update()
                    c.update()
                scene.messageLogged.emit(f"Added chain of {len(chain)} curves")
            return True
        scene.clear_selection()
        for c in chain:
            for pt in c.points:
                sel.points.append(pt)
                pt.update()
            c.update()
        scene.messageLogged.emit(f"Selected chain of {len(chain)} curves")
        return True

    def chain_of(self, curve):
        """The chain containing `curve`, as UI curves. Reads from the model
        (populated by refresh) rather than walking link groups directly."""
        mcurve = self.scene.registry.model_curve_for(curve)
        if mcurve is None:
            return [curve]
        for mchain in self.scene.document.chains:
            if mcurve in mchain.curves:
                return [self.scene.registry.ui_curve_for(mc)
                    for mc in mchain.curves
                    if self.scene.registry.ui_curve_for(mc) is not None]
        return [curve]

    # ------------------------------------------------------------
    #  Loop ordering — junction-tolerant
    # ------------------------------------------------------------
    def _ordered_loop(self, shape):
        """Return [(curve, enter_i), ...] in cyclic order, or None.
        `enter_i` is the index (0 or 1) of the curve's endpoint we enter at."""
        curves = self.scene.ui_curves(shape)
        if not curves:
            return None
        if len(curves) == 1:
            return [(curves[0], 0)]

        def neighbor(c, exit_i):
            end = c.points[0] if exit_i == 0 else c.points[-1]
            g = self.scene.link_manager.group_of(end)
            if g is None:
                return None
            options = []
            for other in curves:
                if other is c:
                    continue
                for i, oe in ((0, other.points[0]), (1, other.points[-1])):
                    if oe in g:
                        options.append((other, i))
                        break
            if len(options) != 1:
                return None  # branching shape → not a simple cycle
            return options[0]

        start = curves[0]
        order = [(start, 0)]
        visited = {start}
        cur, enter_i = start, 0
        while True:
            exit_i = 1 - enter_i
            n = neighbor(cur, exit_i)
            if n is None:
                return None
            nxt, arrive_i = n
            if nxt is start:
                break
            if nxt in visited:
                return None
            order.append((nxt, arrive_i))
            visited.add(nxt)
            cur, enter_i = nxt, arrive_i
        if len(order) != len(curves):
            return None
        return order

    def _loop_segments(self, shape):
        order = self._ordered_loop(shape)
        if order is None:
            return None
        if len(order) == 1:
            c, _ = order[0]
            start_pt = c.points[0]
            c1, c2, end_pt = c.cubic_segment(start_pt)
            return start_pt.pos(), [(c1, c2, end_pt.pos())]

        first_curve, first_enter = order[0]
        start_pt = first_curve.points[first_enter]
        segments = []
        for curve, enter_i in order:
            pt = curve.points[0] if enter_i == 0 else curve.points[-1]
            c1, c2, other = curve.cubic_segment(pt)
            segments.append((c1, c2, other.pos()))
        return start_pt.pos(), segments

    def refresh(self):
        self.scene.registry.sync()
        doc = self.scene.document
        before = set(doc.shapes)
        doc.detect_shapes()
        doc.detect_chains()
        after = set(doc.shapes)

        # Drop fills for dissolved shapes; revert their curves' colours.
        for shape in before - after:
            item = self._fills.pop(shape, None)
            if item is not None:
                self.scene.removeItem(item)
            if shape.color is not None:
                for curve in self.scene.ui_curves(shape):
                    if not any(curve in s.curves for s in after):
                        curve.set_color(self.scene.curve_color)
            if self.scene.selection.is_shape_selected(shape):
                self.deselect(shape)
            self.scene.messageLogged.emit(f"{shape.name} dissolved")

        # Greet new shapes.
        for shape in after - before:
            names = " + ".join(c.name for c in sorted(self.scene.ui_curves(shape), key=lambda c: c.id))
            self.scene.messageLogged.emit(f"{shape.name} formed from {names}")

        self._apply_transparency_to_all()
        self.update_fills()

    def apply_curve_colors(self):
        """Reapply each shape's border color to its curves. Used after the
        scene-wide curve color changes, to keep shape borders distinct."""
        for shape in self.shapes:
            if shape.color is None:
                continue
            border = self._border_color(shape)
            for curve in self.scene.ui_curves(shape):
                curve.set_color(border)

    def reset(self):
        """Drop every shape, every fill, and the model's topology lists."""
        for item in self._fills.values():
            self.scene.removeItem(item)
        self._fills.clear()

        doc = self.scene.document
        doc.extremities.clear()
        doc.controls.clear()
        doc.curves.clear()
        doc.junctions.clear()
        doc.shapes.clear()
        doc.chains.clear()

        self.scene.selection.clear_shapes()

    def rebuild_from_links(self):
        """Drop every fill and force a full re-detection. Called after loading,
        where shapes must be rebuilt from scratch rather than reconciled."""
        for item in self._fills.values():
            self.scene.removeItem(item)
        self._fills.clear()

        # Clearing the model's shape list guarantees detect_shapes() builds
        # fresh Shape objects — no identity from a pre-load document leaks in.
        self.scene.document.shapes.clear()
        self.scene.selection.clear_shapes()

        self.refresh()

    def log_shapes(self):
        """Emit one 'formed from …' message per current shape. Used after
        loading, where signals were blocked during the initial refresh."""
        for shape in self.shapes:
            names = " + ".join(c.name for c in sorted(self.scene.ui_curves(shape), key=lambda c: c.id))
            self.scene.messageLogged.emit(f"{shape.name} formed from {names}")

    def _border_color(self, shape: Shape):
        """Darker variant of the shape's fill, or the scene default."""
        if shape.color is None:
            return self.scene.curve_color
        return shape.color.darker(SHAPE_BORDER_DARKEN)

    def shape_path(self, shape: Shape) -> QPainterPath:
        result = self._loop_segments(shape)
        if result is None:
            return QPainterPath()
        start_pos, segments = result
        path = QPainterPath()
        path.moveTo(start_pos)
        for c1, c2, end_pos in segments:
            path.cubicTo(c1, c2, end_pos)
        path.closeSubpath()
        return path

    def shape_svg_path_string(self, shape: Shape) -> str:
        """SVG `d` attribute for a closed shape. '' if the loop is broken."""
        result = self._loop_segments(shape)
        if result is None:
            return ""
        start_pos, segments = result
        p = SVG_PRECISION
        parts = [f"M {start_pos.x():.{p}f},{start_pos.y():.{p}f}"]
        for c1, c2, end_pos in segments:
            parts.append(
                f"C {c1.x():.{p}f},{c1.y():.{p}f} "
                f"{c2.x():.{p}f},{c2.y():.{p}f} "
                f"{end_pos.x():.{p}f},{end_pos.y():.{p}f}"
            )
        parts.append("Z")
        return " ".join(parts)

    def _rebuild_fill(self, shape):
        if shape.color is None:
            return
        path = self.shape_path(shape)
        if path.isEmpty():
            return

        item = self._fills.get(shape)
        if item is None:
            item = QGraphicsPathItem()
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setZValue(SHAPE_FILL_Z)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(item)
            self._fills[shape] = item

        item.setBrush(QBrush(shape.color))
        item.setPath(path)
        item.setOpacity(SHAPE_TRANSPARENT_OPACITY if self._transparent else 1.0)

    def update_fills(self):
        """Rebuild the fill geometry of every coloured shape. Cheap; called
        after any point move that could have changed a loop's outline."""
        for shape in self.shapes:
            self._rebuild_fill(shape)

    def set_color(self, shape, color):
        shape.color = QColor(color) if color is not None else None

        if shape.color is None:
            item = self._fills.pop(shape, None)
            if item is not None:
                self.scene.removeItem(item)
            for curve in self.scene.ui_curves(shape):
                curve.set_color(self.scene.curve_color)
        else:
            self._rebuild_fill(shape)
            border = self._border_color(shape)
            for curve in self.scene.ui_curves(shape):
                curve.set_color(border)

        self.scene.emit_svg()

