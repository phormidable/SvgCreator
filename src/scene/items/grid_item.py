# scene/items/grid_item.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QPen
from PySide6.QtCore import Qt, QRectF, QPointF

from core.settings import GRID_MINOR_COLOR, GRID_MAJOR_COLOR, GRID_MAJOR_EVERY, GRID_MIN_DEVICE_SPACING

GRID_Z = -50

class GridItem(QGraphicsItem):
    """Horizontal/vertical lines across the artboard. Cosmetic pen (width 0)
    so the spacing is in scene units but each line stays 1 device pixel
    wide at any zoom."""

    def __init__(self, artboard: QRectF, spacing: int):
        super().__init__()
        self._artboard = QRectF(artboard)
        self._spacing = spacing
        self._snap_enabled = False
        self._minor_pen = QPen(GRID_MINOR_COLOR, 0)
        self._major_pen = QPen(GRID_MAJOR_COLOR, 0)
        self.setZValue(GRID_Z)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    # ---- Not hit-testable: can't steal clicks from anything underneath ----
    def shape(self):
        return QPainterPath()

    def boundingRect(self):
        return self._artboard

    # ---- State ----
    def set_spacing(self, spacing: int):
        if spacing == self._spacing:
            return
        self._spacing = spacing
        self.update()

    def set_snap_enabled(self, enabled: bool):
        self._snap_enabled = bool(enabled)

    @property
    def snap_enabled(self) -> bool:
        return self._snap_enabled

    def snap(self, pos: QPointF) -> QPointF:
        """Round `pos` to the nearest multiple of the current spacing, in
        both axes. No-op when snapping is off."""
        if not self._snap_enabled:
            return pos
        s = self._spacing
        return QPointF(round(pos.x() / s) * s, round(pos.y() / s) * s)

    # ---- Paint ----
    def paint(self, painter, option, widget=None):
        scale = painter.transform().m11()
        s = self._spacing
        if scale * s < GRID_MIN_DEVICE_SPACING:
            return

        rect = option.exposedRect
        if rect.isEmpty():
            return

        left, right = rect.left(), rect.right()
        top, bottom = rect.top(), rect.bottom()

        # Pass 1: every line as a minor line.
        painter.setPen(self._minor_pen)
        i0 = int(left // s) - 1
        i1 = int(right // s) + 2
        for i in range(i0, i1):
            x = i * s
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        j0 = int(top // s) - 1
        j1 = int(bottom // s) + 2
        for j in range(j0, j1):
            y = j * s
            painter.drawLine(QPointF(left, y), QPointF(right, y))

        # Pass 2: overlay every Nth line with the major pen.
        ms = s * GRID_MAJOR_EVERY
        painter.setPen(self._major_pen)
        i0 = int(left // ms) - 1
        i1 = int(right // ms) + 2
        for i in range(i0, i1):
            x = i * ms
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        j0 = int(top // ms) - 1
        j1 = int(bottom // ms) + 2
        for j in range(j0, j1):
            y = j * ms
            painter.drawLine(QPointF(left, y), QPointF(right, y))