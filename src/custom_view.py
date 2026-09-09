# custom_view.py
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Signal, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from control_point import ControlPoint

class CustomGraphicsView(QGraphicsView):
    mouseMoved = Signal(object)   # Can emit QPointF or None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: white;")

        self._panning = False
        self._pan_start = None
        self._pan_start_h_scroll = 0
        self._pan_start_v_scroll = 0
        self.mode = "create"

    def set_mode(self, mode):
        self.mode = mode
        if mode == "create":
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode == "edit":
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())
            if not isinstance(item, ControlPoint):
                self._panning = True
                self._pan_start = event.pos()
                self._pan_start_h_scroll = self.horizontalScrollBar().value()
                self._pan_start_v_scroll = self.verticalScrollBar().value()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self.mouseMoved.emit(scene_pos)

        if self._panning:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self._pan_start_h_scroll - delta.x())
            self.verticalScrollBar().setValue(self._pan_start_v_scroll - delta.y())
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        # Emit None when mouse leaves the view
        self.mouseMoved.emit(None)
        super().leaveEvent(event)