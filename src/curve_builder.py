# curve_builder.py
"""CurveBuilder: create-mode state, click handling, and the shared
curve-construction pipeline (used by presets too)."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from bezier_curve import BezierCurve


class CurveBuilder:
    def __init__(self, scene):
        self.scene = scene
        self.current_degree = 2
        self.pending_curve = None

    # ------------------------------------------------------------
    #  Degree
    # ------------------------------------------------------------
    def set_degree(self, degree: int):
        if degree not in (2, 3) or degree == self.current_degree:
            return
        self.current_degree = degree
        if self.pending_curve is not None:
            self.discard()
        self.scene.messageLogged.emit(
            f"Curve type → {'quadratic' if degree == 2 else 'cubic'}")

    # ------------------------------------------------------------
    #  Create-mode click
    # ------------------------------------------------------------
    def handle_click(self, scene_pos):
        if self.pending_curve is None:
            self.pending_curve = BezierCurve(
                self.scene, degree=self.current_degree)
        self.pending_curve.add_point(scene_pos)
        if self.pending_curve.is_complete():
            self.finalize()
            self.scene.messageLogged.emit("Curve created")

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
    def build_from_offsets(self, center: QPointF, offsets, degree: int):
        """Build, commit, and return a curve from offsets around `center`."""
        curve = BezierCurve(self.scene, degree=degree)
        for dx, dy in offsets:
            curve.add_point(QPointF(center.x() + dx, center.y() + dy))
        self.pending_curve = curve
        self.finalize()
        return curve