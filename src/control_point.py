# control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen
from PySide6.QtCore import QPointF

from settings import (POINT_DIAMETER, ENDPOINT_COLOR, ENDPOINT_PEN_COLOR,
                      CONTROL_POINT_COLOR, CONTROL_POINT_PEN_COLOR,
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
        self._apply_style()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    def _apply_style(self):
        if self.highlighted:
            self.setBrush(QBrush(HIGHLIGHT_POINT_COLOR))
            self.setPen(QPen(HIGHLIGHT_POINT_PEN_COLOR, 1.5))
        elif self.hovered:
            self.setBrush(QBrush(HOVER_POINT_COLOR))
            self.setPen(QPen(HOVER_POINT_PEN_COLOR, 1.5))
        elif self.point_idx == 0 or self.point_idx == 3:
            self.setBrush(QBrush(ENDPOINT_COLOR))
            self.setPen(QPen(ENDPOINT_PEN_COLOR, 1.5))
        else:
            self.setBrush(QBrush(CONTROL_POINT_COLOR))
            self.setPen(QPen(CONTROL_POINT_PEN_COLOR, 1.5))

    def set_highlighted(self, value):
        if self.highlighted == value:
            return
        self.highlighted = value
        self._apply_style()

    def set_hovered(self, value):
        if self.hovered == value:
            return
        self.hovered = value
        self._apply_style()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            artboard = self.curve.scene.artboard
            x = min(max(value.x(), artboard.left()), artboard.right())
            y = min(max(value.y(), artboard.top()), artboard.bottom())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.curve.on_point_moved()
        return super().itemChange(change, value)