# scene/curve_builder.py
"""CurveBuilder: create-mode state, click handling, and the shared
curve-construction pipeline (used by presets too)."""

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from scene.items.bezier_curve import BezierCurve

degree_labels = {1: "line", 2: "quadratic", 3: "cubic"}

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
        """Set the curve degree without stroke width (filled curves)."""
        self.set_curve_style(degree, is_stroke=False)

    def set_curve_style(self, degree: int, is_stroke: bool):
        """Set the curve degree and optional stroke width.

        This is the unified method — set_degree delegates here.
        """
        if degree not in degree_labels:
            return

        new_width = self.scene.stroke_width if is_stroke else None
        if degree == self.current_degree and new_width == self.current_stroke_width:
            return

        self.current_degree = degree
        self.current_stroke_width = new_width

        if self.pending_curve is not None:
            self.discard()

        name = degree_labels[degree]
        suffix = " stroke" if is_stroke else ""
        self.scene.messageLogged.emit(f"Curve type → {name}{suffix}")

    def build_from_payload(self, center: QPointF, degree: int, points: list, stroke_width=None):
        """Build a curve from a payload of relative points. Used by clipboard paste."""
        curve = BezierCurve(self.scene, degree=degree, stroke_width=stroke_width)
        for dx, dy in points:
            curve.add_point(QPointF(center.x() + dx, center.y() + dy))
        self.pending_curve = curve
        self.finalize()
        return curve

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
            self.scene.log_and_undo("Curve created", "Create curve")



    # ------------------------------------------------------------
    #  Finalize / discard / clear
    # ------------------------------------------------------------
    def finalize(self):
        ui_curve = self.pending_curve
        self.pending_curve = None

        # 1. Extract positions from the UI curve
        positions = [(pt.pos().x(), pt.pos().y()) for pt in ui_curve.points]

        # 2. Create the model curve via the Document (Single Source of Truth)
        model_curve = self.scene.document.add_curve(ui_curve.degree, positions)

        # 3. Bind the UI curve and its points to the model
        self.scene.registry.bind(ui_curve, model_curve)
        model_points = [model_curve.extremities[0], *model_curve.controls, model_curve.extremities[1]]
        for ui_pt, model_pt in zip(ui_curve.points, model_points):
            self.scene.registry.bind_point(ui_pt, model_pt)

        # 4. Finalize UI state
        ui_curve.committed = True
        for pt in ui_curve.points:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        ui_curve.rebuild_path()

        # 5. Add to scene's UI list (for rendering)
        self.scene.curves.append(ui_curve)
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