# link_indicator.py
from PySide6.QtWidgets import QGraphicsEllipseItem
from PySide6.QtGui import QPen, QPainterPath
from PySide6.QtCore import QTimer, Qt, QPointF

from core.settings import (LINK_INDICATOR_RADIUS, LINK_INDICATOR_COLOR,
    LINK_INDICATOR_PEN_WIDTH, LINK_INDICATOR_FLASH_INTERVAL)


class LinkIndicator(QGraphicsEllipseItem):
    """Flashing circle centered between two points that are about to be linked."""

    def __init__(self):
        r = LINK_INDICATOR_RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.setPen(QPen(LINK_INDICATOR_COLOR, LINK_INDICATOR_PEN_WIDTH))
        self.setBrush(Qt.BrushStyle.NoBrush)
        self.setZValue(1000)                              # on top of everything
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setVisible(False)

        self._flash_on = True
        self._timer = QTimer()
        self._timer.setInterval(LINK_INDICATOR_FLASH_INTERVAL)
        self._timer.timeout.connect(self._toggle_flash)

    def shape(self):
        # Never pickable — so it can't steal clicks from underneath.
        return QPainterPath()

    def _toggle_flash(self):
        self._flash_on = not self._flash_on
        self.setOpacity(1.0 if self._flash_on else 0.25)

    def show_between(self, p1: QPointF, p2: QPointF):
        self.setPos((p1 + p2) / 2)
        self._flash_on = True
        self.setOpacity(1.0)
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()

    def hide_indicator(self):
        self._timer.stop()
        self.setVisible(False)