# scene/items/snap_indicator.py
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QBrush, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem

from core.settings import (
    SNAP_INDICATOR_RADIUS, SNAP_INDICATOR_COLOR, SNAP_INDICATOR_Z,
)


class SnapIndicator(QGraphicsEllipseItem):
    """A red dot marking the grid point a click would snap to. Shown while
    snap-to-grid is on and the mouse is over the canvas. Purely visual: never
    pickable, never moveable.

    Ignores view transforms: the dot stays SNAP_INDICATOR_RADIUS device pixels
    across at any zoom, while its position still follows scene coordinates."""

    def __init__(self):
        r = SNAP_INDICATOR_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setBrush(QBrush(SNAP_INDICATOR_COLOR))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(SNAP_INDICATOR_Z)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setVisible(False)

    def shape(self):
        # Never pickable — clicks pass through to whatever is underneath.
        return QPainterPath()

    def show_at(self, pos: QPointF):
        self.setPos(pos)
        self.setVisible(True)

    def hide_indicator(self):
        self.setVisible(False)