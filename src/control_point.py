# control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen, QPainter
from PySide6.QtCore import QPointF, QRectF, Qt

from settings import (POINT_DIAMETER, CONTROL_POINT_INNER_RADIUS,
                      CONTROL_POINT_RING_COLOR, CONTROL_POINT_RING_PEN_COLOR,
                      HIGHLIGHT_POINT_COLOR, HIGHLIGHT_POINT_PEN_COLOR,
                      HOVER_POINT_COLOR, HOVER_POINT_PEN_COLOR)


class ControlPoint(QGraphicsEllipseItem):
    def __init__(self, pos, curve, point_idx):
        half = POINT_DIAMETER / 2
        super().__init__(-half, -half, POINT_DIAMETER, POINT_DIAMETER)
        self.setPos(pos)
        self.curve = curve
        self.point_idx = point_idx
        self.highlighted = False
        self.hovered = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    def _is_endpoint(self):
        return self.point_idx == 0 or self.point_idx == 3

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Priority: highlight > hover > per-curve color
        if self.highlighted:
            fill, outline, single = HIGHLIGHT_POINT_COLOR, HIGHLIGHT_POINT_PEN_COLOR, True
        elif self.hovered:
            fill, outline, single = HOVER_POINT_COLOR, HOVER_POINT_PEN_COLOR, True
        else:
            fill = self.curve.color
            outline = self.curve.color.darker(150)
            single = self._is_endpoint()

        if single:
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(outline, 1.5))
            painter.drawEllipse(self.rect())
            return

        # Control point: yellow ring, then colored inner disc on top.
        painter.setBrush(QBrush(CONTROL_POINT_RING_COLOR))
        painter.setPen(QPen(CONTROL_POINT_RING_PEN_COLOR, 1.5))
        painter.drawEllipse(self.rect())

        r = CONTROL_POINT_INNER_RADIUS
        inner_rect = QRectF(-r, -r, 2 * r, 2 * r)
        painter.setBrush(QBrush(fill))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(inner_rect)

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            artboard = self.curve.scene.artboard
            x = min(max(value.x(), artboard.left()), artboard.right())
            y = min(max(value.y(), artboard.top()), artboard.bottom())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.curve.on_point_moved()
        return super().itemChange(change, value)