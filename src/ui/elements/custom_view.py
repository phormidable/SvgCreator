# ui/custom_view.py
from PySide6.QtWidgets import QGraphicsView
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTransform
from core.settings import CANVAS_BACKGROUND_COLOR

class CustomGraphicsView(QGraphicsView):
    mouseMoved = Signal(object)
    transformLeftClick = Signal()
    shiftReleased = Signal()
    zoomChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setBackgroundBrush(CANVAS_BACKGROUND_COLOR)

        self._panning = False
        self._pan_start = None
        self._pan_start_h_scroll = 0
        self._pan_start_v_scroll = 0
        self._zoom_factor = 1.0
        self._transform_mode = False

        # Panning is done manually with the right button; never use a drag mode.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._transform_mode:
                self.transformLeftClick.emit()
                event.accept()
                return
        elif event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.pos()
            self._pan_start_h_scroll = self.horizontalScrollBar().value()
            self._pan_start_v_scroll = self.verticalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def set_zoom(self, factor):
        """Set the zoom level, anchored on the viewport centre. Called from the
        combo box and from Ctrl+= / Ctrl+-. Does not emit zoomChanged: the
        caller already knows what it set."""
        if factor == self._zoom_factor:
            return
        anchor = self.mapToScene(self.viewport().rect().center())
        self.setTransform(QTransform().scale(factor, factor))
        self.centerOn(anchor)
        self._zoom_factor = factor

    def _zoom_at_cursor(self, factor, viewport_pos):
        """Set the zoom level, keeping the scene point under `viewport_pos`
        fixed on screen. Called from Ctrl+wheel. Emits zoomChanged so the
        combo box can follow."""
        if factor == self._zoom_factor:
            return
        anchor_scene = self.mapToScene(viewport_pos)
        self.setTransform(QTransform().scale(factor, factor))
        new_vp = self.mapFromScene(anchor_scene)
        dx = new_vp.x() - viewport_pos.x()
        dy = new_vp.y() - viewport_pos.y()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
        self._zoom_factor = factor
        self.zoomChanged.emit(factor)

    def wheelEvent(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        from core.settings import ZOOM_LEVELS
        factors = [f for _, f in ZOOM_LEVELS]
        try:
            idx = factors.index(self._zoom_factor)
        except ValueError:
            idx = min(range(len(factors)),
                      key=lambda i: abs(factors[i] - self._zoom_factor))
        new_idx = max(0, min(len(factors) - 1,
                             idx + (1 if delta > 0 else -1)))
        if new_idx == idx:
            event.accept()
            return
        self._zoom_at_cursor(factors[new_idx], event.position().toPoint())
        event.accept()

    def set_transform_mode(self, active: bool):
        self._transform_mode = active
        self.setCursor(Qt.CursorShape.SizeAllCursor if active
                       else Qt.CursorShape.ArrowCursor)

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

    def keyPressEvent(self, event):
        # Let Shift+arrows escape the view so MainWindow can nudge selected points.
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            event.ignore()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Auto-repeat sends repeated keyReleaseEvent for held keys; the
        # isAutoRepeat flag lets us ignore those. Modifier keys usually
        # don't auto-repeat, but checking is cheap and correct.
        if event.key() == Qt.Key.Key_Shift and not event.isAutoRepeat():
            self.shiftReleased.emit()
        super().keyReleaseEvent(event)