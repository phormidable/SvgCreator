# scene/curve_builder.py
"""CurveBuilder: create-mode state, click handling, and the shared
curve-construction pipeline (used by presets too)."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from scene.items.bezier_curve import BezierCurve
from core.settings import STROKE_DEFAULT_WIDTH

class CurveBuilder:
    def __init__(self, scene):
        self.scene = scene
        self.current_degree = 2
        self.pending_curve = None
        self.current_stroke_width = None

        # ------------------------------------------------------------
    #  Degree
    # ------------------------------------------------------------
    def set_degree(self, degree: int):
        if degree not in (1, 2, 3) or degree == self.current_degree:
            return
        self.current_degree = degree
        if self.pending_curve is not None:
            self.discard()
        label = {1: "line", 2: "quadratic", 3: "cubic"}[degree]
        self.scene.messageLogged.emit(f"Curve type → {label}")

    def set_curve_style(self, degree: int, is_stroke: bool):
        new_width = STROKE_DEFAULT_WIDTH if is_stroke else None
        if degree not in (1, 2, 3):
            return
        if degree == self.current_degree and new_width == self.current_stroke_width:
            return
        self.current_degree = degree
        self.current_stroke_width = new_width
        if self.pending_curve is not None:
            self.discard()
        name = {1: "line", 2: "quadratic", 3: "cubic"}[degree]
        suffix = " stroke" if is_stroke else ""
        self.scene.messageLogged.emit(f"Curve type → {name}{suffix}")

    # ------------------------------------------------------------
    #  Create-mode click
    # ------------------------------------------------------------
    def handle_click(self, scene_pos):
        pos = self.scene.grid_item.snap(scene_pos)
        if self.pending_curve is None:
            self.pending_curve = BezierCurve(
                self.scene,
                degree=self.current_degree,
                stroke_width=self.current_stroke_width,
            )
        self.pending_curve.add_point(pos)
        if self.pending_curve.is_complete():
            self.finalize()
            self.scene.messageLogged.emit("Curve created")
            self.scene.undo.push("Create curve")



    # ------------------------------------------------------------
    #  Finalize / discard / clear
    # ------------------------------------------------------------
    def finalize(self):
        curve = self.pending_curve
        self.pending_curve = None
        curve.committed = True
        for pt in curve.points:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        curve.rebuild_path()
        self.scene.curves.append(curve)
        self.scene.emit_svg()

    def discard(self):
        if self.pending_curve is None:
            return
        self.pending_curve.dispose()
        self.pending_curve = None
        self.scene.emit_svg()
        self.scene.messageLogged.emit("Incomplete curve discarded")

    def build_line_between(self, p1: QPointF, p2: QPointF):
        """Create and commit a degree-1 line between two positions. Returns
        the curve. Caller is responsible for linking (or not) and undo push."""
        curve = BezierCurve(self.scene, degree=1)
        curve.add_point(QPointF(p1))
        curve.add_point(QPointF(p2))
        self.pending_curve = curve
        self.finalize()
        return curve

    def clear(self):
        """Dispose the pending curve silently. Used by clear_all."""
        if self.pending_curve is not None:
            self.pending_curve.dispose()
            self.pending_curve = None

    def cancel_pending_curve(self) -> bool:
        if self.scene.mode == "create" and self.pending_curve is not None:
            self.discard()
            return True
        return False

    # ------------------------------------------------------------
    #  Preset helper
    # ------------------------------------------------------------
    def build_from_offsets(self, center, offsets, degree, stroke_width=None):
        curve = BezierCurve(self.scene, degree=degree, stroke_width=stroke_width)
        for dx, dy in offsets:
            curve.add_point(QPointF(center.x() + dx, center.y() + dy))
        self.pending_curve = curve
        self.finalize()
        return curve