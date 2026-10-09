# scene/point_renderer.py
"""PointRenderer: the painting logic for ControlPoint.

ControlPoint delegates to it, so no pen/brush selection lives on the item.
Point state (hovered, selected, focused, linked, is_endpoint) is read at
paint time through the item's properties — nothing is cached here.
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBrush, QColor, QPen, QPainter

from core.settings import (POINT_RADIUS, LINKED_RING_COLOR, LINKED_RING_PEN_WIDTH, LINKED_RING_EXTRA,
    HOVER_COLOR, HOVER_COLOR_FOCUS, HOVER_POINT_PEN_COLOR, SELECTED_POINT_COLOR, SELECTED_POINT_PEN_COLOR,
    SELECTED_POINT_OUTER_COLOR, SELECTED_POINT_OUTER_WIDTH, POINT_BLUE, ENDPOINT_ALPHA, ENDPOINT_PEN_COLOR,
    CONTROL_POINT_OUTER_PEN_COLOR, CONTROL_POINT_MIDDLE_RADIUS, CONTROL_POINT_MIDDLE_COLOR, CONTROL_POINT_MIDDLE_PEN_COLOR,
    CONTROL_POINT_INNER_RADIUS, CONTROL_POINT_INNER_COLOR)


class PointRenderer:
    def __init__(self, scene):
        self.scene = scene

    # ------------------------------------------------------------
    #  Entry point
    # ------------------------------------------------------------
    def draw(self, painter: QPainter, point):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if point.linked:
            self._draw_linked_ring(painter)

        # Persistent selection wins.
        if point.selected:
            self._draw_selected(painter, point)
            return
        # Focus (mouse directly on this point) beats group hover.
        if point.focused:
            self._draw_solid(painter, point, HOVER_COLOR_FOCUS, HOVER_POINT_PEN_COLOR)
            return
        if point.hovered:
            self._draw_solid(painter, point, HOVER_COLOR, HOVER_POINT_PEN_COLOR)
            return

        if point.is_endpoint():
            self._draw_endpoint(painter, point)
        else:
            self._draw_control_point(painter, point)

    # ------------------------------------------------------------
    #  Pieces
    # ------------------------------------------------------------
    def _ellipse(self, painter, rect, brush, pen):
        """Set brush and pen, then draw one ellipse. Pass Qt.BrushStyle.NoBrush
        or Qt.PenStyle.NoPen when you want either suppressed."""
        painter.setBrush(brush)
        painter.setPen(pen)
        painter.drawEllipse(rect)

    def _draw_linked_ring(self, painter):
        r = POINT_RADIUS + LINKED_RING_EXTRA
        self._ellipse(painter, QRectF(-r, -r, 2 * r, 2 * r), Qt.BrushStyle.NoBrush, QPen(LINKED_RING_COLOR, LINKED_RING_PEN_WIDTH))

    def _draw_solid(self, painter, point, fill, outline):
        self._ellipse(painter, point.rect(), QBrush(fill), QPen(outline, 1.5))

    def _draw_selected(self, painter, point):
        # Green outer ring, on the point's own outline.
        self._ellipse(painter, point.rect(), Qt.BrushStyle.NoBrush, QPen(SELECTED_POINT_OUTER_COLOR, SELECTED_POINT_OUTER_WIDTH))

        # Red inner disc, pulled inward so the ring is visible.
        r = POINT_RADIUS - SELECTED_POINT_OUTER_WIDTH
        self._ellipse(painter, QRectF(-r, -r, 2 * r, 2 * r), QBrush(SELECTED_POINT_COLOR), QPen(SELECTED_POINT_PEN_COLOR, 1.0))

    def _draw_endpoint(self, painter, point):
        c = QColor(POINT_BLUE)
        c.setAlpha(ENDPOINT_ALPHA)
        self._ellipse(painter, point.rect(), QBrush(c), QPen(ENDPOINT_PEN_COLOR, 1.5))

    def _draw_control_point(self, painter, point):
        # Outer blue disc (radius POINT_RADIUS)
        self._ellipse(painter, point.rect(), QBrush(POINT_BLUE), QPen(CONTROL_POINT_OUTER_PEN_COLOR, 1.5))

        # Middle white disc
        r = CONTROL_POINT_MIDDLE_RADIUS
        self._ellipse(painter, QRectF(-r, -r, 2 * r, 2 * r), QBrush(CONTROL_POINT_MIDDLE_COLOR), QPen(CONTROL_POINT_MIDDLE_PEN_COLOR, 1.0))

        # Inner yellow disc
        r = CONTROL_POINT_INNER_RADIUS
        self._ellipse(painter, QRectF(-r, -r, 2 * r, 2 * r), QBrush(CONTROL_POINT_INNER_COLOR), Qt.PenStyle.NoPen)