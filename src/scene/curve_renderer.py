# scene/curve_renderer.py
"""CurveRenderer: builds visual and hit paths for curves, and selects the
pen that reflects a curve's current interaction state.

Lives on the scene as `scene.curve_renderer`. BezierCurve delegates to it
in paint() and rebuild_path(), so no QPen or path-construction logic
lives on the item itself.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen

from core.settings import (CURVE_PEN_WIDTH,HOVER_COLOR, HOVER_COLOR_FOCUS, HIDDEN_CURVE_COLOR, SHAPE_SELECTED_CURVE_COLOR,
                           SHAPE_SELECTED_CURVE_PEN_WIDTH, CURVE_SELECTED_PEN_COLOR, CURVE_SELECTED_PEN_WIDTH, HOVER_TOLERANCE)


from scene.helpers import make_round_pen

class CurveRenderer:
    def __init__(self, scene):
        self.scene = scene

        # Static pens — one per interaction state, built once.
        self._pen_hover = make_round_pen(HOVER_COLOR, CURVE_PEN_WIDTH)
        self._pen_focus = make_round_pen(HOVER_COLOR_FOCUS, CURVE_PEN_WIDTH)
        self._pen_hidden = make_round_pen(HIDDEN_CURVE_COLOR, CURVE_PEN_WIDTH)
        self._pen_shape_selected = make_round_pen( SHAPE_SELECTED_CURVE_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH)
        self._pen_curve_selected = make_round_pen( CURVE_SELECTED_PEN_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH)

    # ------------------------------------------------------------
    #  Paths
    # ------------------------------------------------------------
    @staticmethod
    def paths_for(positions, degree, stroke_width=None):
        path = QPainterPath()
        if len(positions) == degree + 1:
            path.moveTo(positions[0])
            if degree == 1:
                path.lineTo(positions[1])
            elif degree == 2:
                path.quadTo(positions[1], positions[2])
            else:
                path.cubicTo(positions[1], positions[2], positions[3])
        elif positions:
            path.moveTo(positions[0])
            for p in positions[1:]:
                path.lineTo(p)

        stroker = QPainterPathStroker()
        hit_width = max(2 * HOVER_TOLERANCE,
                        (stroke_width or 0) + 2 * HOVER_TOLERANCE)
        stroker.setWidth(hit_width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return path, stroker.createStroke(path)

    # ------------------------------------------------------------
    #  Pens
    # ------------------------------------------------------------
    def pen_for(self, ui_curve) -> QPen:
        w = (ui_curve.start_width if ui_curve.start_width is not None
             else CURVE_PEN_WIDTH)
        if ui_curve.shape_selected:
            return make_round_pen(SHAPE_SELECTED_CURVE_COLOR, max(w, SHAPE_SELECTED_CURVE_PEN_WIDTH))
        if ui_curve.curve_selected:
            return make_round_pen(CURVE_SELECTED_PEN_COLOR, max(w, CURVE_SELECTED_PEN_WIDTH))
        if ui_curve.focused:
            return make_round_pen(HOVER_COLOR_FOCUS, w) if w != CURVE_PEN_WIDTH else self._pen_focus
        if ui_curve.hovered:
            return make_round_pen(HOVER_COLOR, w) if w != CURVE_PEN_WIDTH else self._pen_hover
        if ui_curve.points_hidden:
            return make_round_pen(HIDDEN_CURVE_COLOR, w) if w != CURVE_PEN_WIDTH else self._pen_hidden
        return ui_curve.pen
