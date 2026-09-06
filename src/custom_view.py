# custom_view.py
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Signal, QPointF
from PySide6.QtGui import QMouseEvent

class CustomGraphicsView(QGraphicsView):
    mouseMoved = Signal(QPointF)   # emits scene coordinates

    def mouseMoveEvent(self, event: QMouseEvent):
        scene_pos = self.mapToScene(event.pos())
        self.mouseMoved.emit(scene_pos)
        super().mouseMoveEvent(event)