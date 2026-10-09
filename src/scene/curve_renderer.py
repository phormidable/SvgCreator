# scene/curve_renderer.py
"""CurveRenderer: builds visual and hit paths for curves, and selects the
pen that reflects a curve's current interaction state.

Lives on the scene as `scene.curve_renderer`. BezierCurve delegates to it
in paint() and rebuild_path(), so no QPen or path-construction logic
lives on the item itself.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen

from core.settings import (
    CURVE_PEN_WIDTH,
    HOVER_COLOR, HOVER_COLOR_FOCUS, HIDDEN_CURVE_COLOR,
    SHAPE_SELECTED_CURVE_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH,
    CURVE_SELECTED_PEN_COLOR, CURVE_SELECTED_PEN_WIDTH,
    HOVER_TOLERANCE,
)


class CurveRenderer:
    def __init__(self, scene):
        self.scene = scene

        # Static pens — one per interaction state, built once.
        self._pen_hover = QPen(HOVER_COLOR, CURVE_PEN_WIDTH)
        self._pen_focus = QPen(HOVER_COLOR_FOCUS, CURVE_PEN_WIDTH)
        self._pen_hidden = QPen(HIDDEN_CURVE_COLOR, CURVE_PEN_WIDTH)
        self._pen_shape_selected = QPen(SHAPE_SELECTED_CURVE_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH)
        self._pen_curve_selected = QPen(CURVE_SELECTED_PEN_COLOR, CURVE_SELECTED_PEN_WIDTH)

    # ------------------------------------------------------------
    #  Pens
    # ------------------------------------------------------------
    def pen_for(self, ui_curve) -> QPen:
        # Persistent selection wins over transient hover/focus.
        if ui_curve.shape_selected:
            return self._pen_shape_selected
        if ui_curve.curve_selected:
            return self._pen_curve_selected
        # Focus (mouse directly on the stroke) beats group hover.
        if ui_curve.focused:
            return self._pen_focus
        if ui_curve.hovered:
            return self._pen_hover
        if ui_curve.points_hidden:
            return self._pen_hidden
        return QPen(ui_curve.color, CURVE_PEN_WIDTH)

    # ------------------------------------------------------------
    #  Paths
    # ------------------------------------------------------------
    def paths_for(self, positions, degree):
        """Build (visual, hit) paths from a list of QPointF positions.

        Handles partial curves — fewer than degree+1 points draws a
        polyline preview, matching the pre-refactor behaviour so the
        in-progress curve still shows while the user places points."""
        path = QPainterPath()
        if len(positions) == degree + 1:
            path.moveTo(positions[0])
            if degree == 2:
                path.quadTo(positions[1], positions[2])
            else:
                path.cubicTo(positions[1], positions[2], positions[3])
        elif positions:
            path.moveTo(positions[0])
            for p in positions[1:]:
                path.lineTo(p)

        stroker = QPainterPathStroker()
        stroker.setWidth(2 * HOVER_TOLERANCE)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return path, stroker.createStroke(path)