# custom_view.py
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Signal, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from control_point import ControlPoint

class CustomGraphicsView(QGraphicsView):
    mouseMoved = Signal(QPointF)   # emits scene coordinates

    def __init__(self, parent=None):
        super().__init__(parent)
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
            # Check if we clicked on a ControlPoint
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, self.transform())
            if not isinstance(item, ControlPoint):
                # Start panning
                self._panning = True
                self._pan_start = event.pos()
                self._pan_start_h_scroll = self.horizontalScrollBar().value()
                self._pan_start_v_scroll = self.verticalScrollBar().value()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return  # Do not call super, we handle it

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Emit mouse coordinates
        scene_pos = self.mapToScene(event.pos())
        self.mouseMoved.emit(scene_pos)

        if self._panning:
            delta = event.pos() - self._pan_start
            self.horizontalScrollBar().setValue(self._pan_start_h_scroll - delta.x())
            self.verticalScrollBar().setValue(self._pan_start_v_scroll - delta.y())
            return  # Do not call super to avoid default drag behavior

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        super().mouseReleaseEvent(event)