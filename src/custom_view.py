# custom_view.py
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Signal, Qt


class CustomGraphicsView(QGraphicsView):
    mouseMoved = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: white;")

        self._panning = False
        self._pan_start = None
        self._pan_start_h_scroll = 0
        self._pan_start_v_scroll = 0
        self.mode = "create"

        # Panning is done manually with the right button; never use a drag mode.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def set_mode(self, mode):
        self.mode = mode
        # Nothing to change here anymore — panning is right-button only.

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.pos()
            self._pan_start_h_scroll = self.horizontalScrollBar().value()
            self._pan_start_v_scroll = self.verticalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
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
        if self._panning and event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.mouseMoved.emit(None)
        super().leaveEvent(event)