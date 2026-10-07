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
from settings import SVG_PRECISION, SHAPE_BORDER_DARKEN, SHAPE_TRANSPARENT_OPACITY
from shape import Shape

SHAPE_FILL_Z = -10

class ShapeManager:
    def __init__(self, scene):
        self.scene = scene
        self.shapes: list[Shape] = []
        self._selected_shapes: set[Shape] = set()
        self._transparent = False
        self._shaped_curves: set = set()  # curves whose opacity we last set
        self._last_opacity: float = 1.0  # value we last applied to those curves

    # ------------------------------------------------------------
    #  Selection
    # ------------------------------------------------------------
    def selected(self) -> Shape | None:
        """First selected shape, or None. Convenience for single-selection UIs."""
        return next(iter(self._selected_shapes), None)

    def selected_shapes(self) -> list[Shape]:
        return list(self._selected_shapes)

    def select(self, shape: Shape | None, add: bool = False):
        if shape is None:
            for s in self._selected_shapes:
                s.set_selected(False)
            self._selected_shapes.clear()
            return
        if add:
            if shape not in self._selected_shapes:
                self._selected_shapes.add(shape)
                shape.set_selected(True)
            return
        # Replace: drop every other selected shape.
        for s in list(self._selected_shapes):
            if s is not shape:
                s.set_selected(False)
                self._selected_shapes.discard(s)
        if shape not in self._selected_shapes:
            self._selected_shapes.add(shape)
            shape.set_selected(True)

    def deselect(self, shape: Shape):
        if shape in self._selected_shapes:
            shape.set_selected(False)
            self._selected_shapes.discard(shape)

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
            shaped.update(shape.curves)

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

        # Fill items: cheap, just iterate shapes (one per shape, not per point).
        for shape in self.shapes:
            if shape.fill_item is not None:
                shape.fill_item.setOpacity(opacity)

    @staticmethod
    def _set_curve_opacity(curve, opacity):
        curve.setOpacity(opacity)
        for pt in curve.points:
            pt.setOpacity(opacity)

    def shape_of_curve(self, curve) -> Shape | None:
        for shape in self.shapes:
            if curve in shape.curves:
                return shape
        return None

    def select_from_hover(self, add: bool = False) -> bool:
        hovered = self.scene.hovered_curve
        if hovered is None:
            return False
        shape = self.shape_of_curve(hovered)
        if shape is None:
            self.scene.messageLogged.emit(f"{hovered.name} is not part of a shape")
            return False

        if add:
            if shape in self._selected_shapes:
                self.deselect(shape)
                self.scene.messageLogged.emit(f"{shape.name} removed from selection")
            else:
                self.select(shape, add=True)
                self.scene.messageLogged.emit(f"Added {shape.name} to selection")
            return True

        # No shift: replace, unless this shape is already the whole selection.
        if self._selected_shapes == {shape}:
            self.select(None)
            self.scene.messageLogged.emit(f"{shape.name} deselected")
        else:
            self.select(shape, add=False)
            self.scene.messageLogged.emit(f"{shape.name} selected")
        return True

    # ------------------------------------------------------------
    #  Detection
    # ------------------------------------------------------------
    def _pair_partner(self, pt):
        if not pt.is_endpoint():
            return None
        g = self.scene.link_manager.group_of(pt)
        if g is None or len(g) != 2:
            return None
        other = g[0] if g[1] is pt else g[1]
        if not other.is_endpoint():
            return None
        return other

    def _trace_loop_from(self, start_pt):
        """Walk from `start_pt` through link partners. Return the frozenset of
        curves if the walk returns to `start_pt`; otherwise None."""
        if self._pair_partner(start_pt) is None:
            return None
        current_pt = start_pt
        visited: list = []
        while True:
            partner = self._pair_partner(current_pt)
            if partner is None:
                return None                       # dead end
            next_curve = partner.curve
            if next_curve in visited:
                return None                       # revisited without closing
            visited.append(next_curve)
            other = (next_curve.points[-1] if partner is next_curve.points[0] else next_curve.points[0])
            if other is start_pt:
                return frozenset(visited)         # closed
            current_pt = other

    def refresh(self):
        """Rebuild self.shapes from the current link topology. Existing Shape
        objects (and their names) are reused when the loop is unchanged.
        Emits 'formed' / 'dissolved' messages for the diff."""
        found: list[frozenset] = []
        seen: set[frozenset] = set()
        for curve in self.scene.curves:
            if not curve.is_complete():
                continue
            for idx in (0, -1):
                loop = self._trace_loop_from(curve.points[idx])
                if loop and loop not in seen:
                    seen.add(loop)
                    found.append(loop)

        existing = {shape.curves: shape for shape in self.shapes}
        new_shapes: list[Shape] = []
        for curves in found:
            if curves in existing:
                new_shapes.append(existing[curves])
            else:
                shape = Shape(curves)
                new_shapes.append(shape)
                names = " + ".join(c.name for c in sorted(curves, key=lambda c: c.id))
                self.scene.messageLogged.emit(f"{shape.name} formed from {names}")

        # Drop any selected shape that was dissolved.
        for shape in list(self._selected_shapes):
            if shape not in new_shapes:
                self.deselect(shape)
                self.scene.messageLogged.emit(f"{shape.name} dissolved")

        self.shapes = new_shapes

        self._apply_transparency_to_all()
        self.update_fills()

    def apply_curve_colors(self):
        """Reapply each shape's border color to its curves. Used after the
        scene-wide curve color changes, to keep shape borders distinct."""
        for shape in self.shapes:
            if shape.color is None:
                continue
            border = self._border_color(shape)
            for curve in shape.curves:
                curve.set_color(border)

    def rebuild_from_links(self):
        """Reset shape state and re-detect all loops (used after loading)."""
        for shape in self.shapes:
            if shape.fill_item is not None:
                self.scene.removeItem(shape.fill_item)
                shape.fill_item = None
        self.shapes.clear()
        Shape._next_id = 1
        self.refresh()

    def log_shapes(self):
        """Emit one 'formed from …' message per current shape. Used after
        loading, where signals were blocked during the initial refresh."""
        for shape in self.shapes:
            names = " + ".join(c.name for c in sorted(shape.curves, key=lambda c: c.id))
            self.scene.messageLogged.emit(f"{shape.name} formed from {names}")

    def _border_color(self, shape: Shape):
        """Darker variant of the shape's fill, or the scene default."""
        if shape.color is None:
            return self.scene.curve_color
        return shape.color.darker(SHAPE_BORDER_DARKEN)

    # ------------------------------------------------------------
    #  Fill
    # ------------------------------------------------------------
    def _loop_segments(self, shape: Shape):
        """Return (start_pos, [(c1, c2, end_pos), ...]) for the closed loop,
        or None if the topology is broken."""
        if not shape.curves:
            return None
        start_pt = None
        for curve in shape.curves:
            for idx in (0, -1):
                if self._pair_partner(curve.points[idx]) is not None:
                    start_pt = curve.points[idx]
                    break
            if start_pt is not None:
                break

        segments = []
        current = start_pt
        seen: set = set()
        while True:
            curve = current.curve
            if curve in seen:
                return None
            seen.add(curve)
            c1, c2, other = curve.cubic_segment(current)
            segments.append((c1, c2, other.pos()))
            nxt = self._pair_partner(other)
            if nxt is None:
                return None
            if nxt is start_pt:
                return start_pt.pos(), segments
            current = nxt

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

    def _rebuild_fill(self, shape: Shape):
        if shape.color is None:
            return
        path = self.shape_path(shape)
        if path.isEmpty():
            return
        if shape.fill_item is None:
            item = QGraphicsPathItem()
            item.setPen(QPen(Qt.PenStyle.NoPen))
            item.setZValue(SHAPE_FILL_Z)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(item)
            shape.fill_item = item
        shape.fill_item.setBrush(QBrush(shape.color))
        shape.fill_item.setPath(path)
        shape.fill_item.setOpacity(
            SHAPE_TRANSPARENT_OPACITY if self._transparent else 1.0)

    def update_fills(self):
        """Rebuild the fill geometry of every coloured shape. Cheap; called
        after any point move that could have changed a loop's outline."""
        for shape in self.shapes:
            self._rebuild_fill(shape)

    def set_color(self, shape: Shape, color: QColor | None):
        shape.color = QColor(color) if color is not None else None
        if shape.color is None:
            if shape.fill_item is not None:
                self.scene.removeItem(shape.fill_item)
                shape.fill_item = None
            for curve in shape.curves:
                curve.set_color(self.scene.curve_color)
        else:
            self._rebuild_fill(shape)
            border = self._border_color(shape)
            for curve in shape.curves:
                curve.set_color(border)
        self.scene.emit_svg()

    # ------------------------------------------------------------
    #  Reset
    # ------------------------------------------------------------
    def reset(self):
        """Drop every shape and its fill (used by clear_all)."""
        for shape in self.shapes:
            if shape.fill_item is not None:
                self.scene.removeItem(shape.fill_item)
                shape.fill_item = None
        self.shapes.clear()
        self._selected_shapes.clear()
        self._transparent = False
        self._shaped_curves = set()
        self._last_opacity = 1.0
        Shape._next_id = 1