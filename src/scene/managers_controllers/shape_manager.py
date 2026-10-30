# scene/managers_controllers/shape_manager.py

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
    def _loop_segments(self, shape):
        """Return (start_pos, [(c1, c2, end_pos), ...]) for the closed loop,
        or None if the topology is broken. Walks shape.curves in the cyclic
        order the model already stored."""
        ui_curves = self.scene.ui_curves(shape)
        if not ui_curves:
            return None

        start_pt = self._loop_start_point(ui_curves)
        if start_pt is None:
            return None

        segments = []
        current = start_pt
        for curve in ui_curves:
            entry = self._shared_endpoint(curve, current)
            if entry is None:
                return None
            c1, c2, other = curve.cubic_segment(entry)
            segments.append((c1, c2, other.pos()))
            current = other
        return start_pt.pos(), segments

    def _loop_start_point(self, ui_curves):
        """An endpoint of the first curve that shares a junction with the last
        curve's far end — i.e. the curve's entry point in the cycle."""
        first = ui_curves[0]
        endpoints = (first.points[0], first.points[-1])
        if len(ui_curves) == 1:
            return endpoints[0]  # teardrop: either will do
        last = ui_curves[-1]
        for p in endpoints:
            g = self.scene.link_manager.group_of(p)
            if g and any(q.curve is last for q in g):
                return p
        return None

    def _shared_endpoint(self, curve, other_pt):
        """An endpoint of `curve` that is `other_pt` or shares its junction."""
        endpoints = (curve.points[0], curve.points[-1])
        if other_pt in endpoints:
            return other_pt
        g = self.scene.link_manager.group_of(other_pt)
        if g is None:
            return None
        for p in endpoints:
            if p in g:
                return p
        return None

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
                self.scene.selection.deselect_shape(shape)
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

    def shape_path(self, shape) -> QPainterPath:
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
