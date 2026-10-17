# scene/items/origin_marker.py
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem

from core.settings import (
    ORIGIN_MARKER_COLOR, ORIGIN_MARKER_PEN_WIDTH,
    ORIGIN_MARKER_ARM, ORIGIN_MARKER_Z,
)


class OriginMarker(QGraphicsItem):
    """A small dashed cross at scene (0, 0). Ignores view transforms, so it
    stays a constant size on screen at any zoom — a UI landmark, not drawing
    content. Never pickable."""

    def __init__(self):
        super().__init__()
        self.setPos(0, 0)
        self.setZValue(ORIGIN_MARKER_Z)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        pen = QPen(ORIGIN_MARKER_COLOR, ORIGIN_MARKER_PEN_WIDTH)
        pen.setStyle(Qt.PenStyle.DashLine)
        self._pen = pen

    def boundingRect(self):
        r = ORIGIN_MARKER_ARM + ORIGIN_MARKER_PEN_WIDTH
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        # Never pickable — clicks pass through.
        return QPainterPath()

    def paint(self, painter, option, widget=None):
        painter.setPen(self._pen)
        a = ORIGIN_MARKER_ARM
        painter.drawLine(QPointF(-a, 0), QPointF(a, 0))
        painter.drawLine(QPointF(0, -a), QPointF(0, a))