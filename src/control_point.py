# control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen, QPainter, QColor
from PySide6.QtCore import QPointF, Qt, QRectF

from settings import (POINT_DIAMETER, LINKED_RING_EXTRA, LINKED_RING_PEN_WIDTH, POINT_RADIUS, HIGHLIGHT_POINT_COLOR,
            HIGHLIGHT_POINT_PEN_COLOR, HOVER_COLOR_FOCUS, HOVER_POINT_PEN_COLOR, SELECTED_POINT_OUTER_COLOR, SELECTED_POINT_OUTER_WIDTH,
                      SELECTED_POINT_COLOR, SELECTED_POINT_PEN_COLOR, LINKED_RING_COLOR, POINT_BLUE, ENDPOINT_ALPHA, ENDPOINT_PEN_COLOR,
                      CONTROL_POINT_OUTER_PEN_COLOR, CONTROL_POINT_MIDDLE_RADIUS, CONTROL_POINT_MIDDLE_COLOR, CONTROL_POINT_MIDDLE_PEN_COLOR,
                      CONTROL_POINT_INNER_RADIUS, CONTROL_POINT_INNER_COLOR, HOVER_COLOR)

class ControlPoint(QGraphicsEllipseItem):
    def __init__(self, pos, curve, point_idx):
        half = POINT_DIAMETER / 2
        super().__init__(-half, -half, POINT_DIAMETER, POINT_DIAMETER)
        self.setPos(pos)
        self.curve = curve
        self.point_idx = point_idx # 0..3, fixed for the lifetime of the curve
        self.highlighted = False
        self.hovered = False
        self.selected = False
        self.linked = False
        self.focused = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    def is_endpoint(self):
        return self.point_idx == 0 or self.point_idx == self.curve.degree

    def boundingRect(self):
        if self.linked:
            half = POINT_DIAMETER / 2 + LINKED_RING_EXTRA + LINKED_RING_PEN_WIDTH
            return QRectF(-half, -half, 2 * half, 2 * half)
        return super().boundingRect()

    def set_linked(self, value):
        if self.linked == value:
            return
        self.prepareGeometryChange()  # boundingRect() is about to change
        self.linked = value
        self.update()

    def set_focused(self, value):
        if self.focused == value:
            return
        self.focused = value
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self.linked:
            r = POINT_RADIUS + LINKED_RING_EXTRA
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(LINKED_RING_COLOR, LINKED_RING_PEN_WIDTH))
            painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

        # Override states draw one solid disc and stop.
        if self.hovered:
            self._draw_solid(painter, HOVER_COLOR, HOVER_POINT_PEN_COLOR)
            return
        if self.selected:
            self._draw_selected(painter)
            return
        if self.focused:
            self._draw_solid(painter, HOVER_COLOR_FOCUS, HOVER_POINT_PEN_COLOR)
            return
        if self.highlighted:
            self._draw_solid(painter, HIGHLIGHT_POINT_COLOR, HIGHLIGHT_POINT_PEN_COLOR)
            return

        if self.is_endpoint():
            self._draw_endpoint(painter)
        else:
            self._draw_control_point(painter)

    def _draw_solid(self, painter, fill, outline):
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(outline, 1.5))
        painter.drawEllipse(self.rect())

    def _draw_selected(self, painter):
        # Green outer ring, on the point's own outline.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(SELECTED_POINT_OUTER_COLOR, SELECTED_POINT_OUTER_WIDTH))
        painter.drawEllipse(self.rect())

        # Red inner disc, pulled inward so the ring is visible.
        r = POINT_RADIUS - SELECTED_POINT_OUTER_WIDTH
        painter.setBrush(QBrush(SELECTED_POINT_COLOR))
        painter.setPen(QPen(SELECTED_POINT_PEN_COLOR, 1.0))
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def _draw_endpoint(self, painter):
        c = QColor(POINT_BLUE)
        c.setAlpha(ENDPOINT_ALPHA)
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(ENDPOINT_PEN_COLOR, 1.5))
        painter.drawEllipse(self.rect())

    def _draw_control_point(self, painter):
        # Outer blue disc (radius POINT_RADIUS)
        painter.setBrush(QBrush(POINT_BLUE))
        painter.setPen(QPen(CONTROL_POINT_OUTER_PEN_COLOR, 1.5))
        painter.drawEllipse(self.rect())

        # Middle white disc
        r = CONTROL_POINT_MIDDLE_RADIUS
        painter.setBrush(QBrush(CONTROL_POINT_MIDDLE_COLOR))
        painter.setPen(QPen(CONTROL_POINT_MIDDLE_PEN_COLOR, 1.0))
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

        # Inner yellow disc
        r = CONTROL_POINT_INNER_RADIUS
        painter.setBrush(QBrush(CONTROL_POINT_INNER_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-r, -r, 2 * r, 2 * r))

    def set_highlighted(self, value):
        if self.highlighted == value:
            return
        self.highlighted = value
        self.update()

    def set_hovered(self, value):
        if self.hovered == value:
            return
        self.hovered = value
        self.update()

    def set_selected(self, value):
        if self.selected == value:
            return
        self.selected = value
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.curve.scene()
            if scene is None:
                return value  # no clamping possible; accept as-is
            artboard = self.curve.scene().artboard
            x = min(max(value.x(), artboard.left()), artboard.right())
            y = min(max(value.y(), artboard.top()), artboard.bottom())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.curve.scene()
            if scene is not None:
                scene.link_manager.propagate_move(self, self.pos())
                self.curve.on_point_moved()
                scene.on_point_moved(self)  # ← new: notify about *this* point
        return super().itemChange(change, value)