# preview_widget.py
"""PreviewWidget: paints a background pixmap (semi-transparent, centred)
then renders the current SVG on top. Right-drag pans the view; zoom is
driven externally via set_zoom()."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QByteArray, QPointF
from PySide6.QtGui import QPainter, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer

BACKGROUND_OPACITY = 0.35


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        self._renderer: QSvgRenderer | None = None
        self._zoom = 1.0
        self._offset = QPointF(0, 0)

        self._panning = False
        self._pan_start = QPointF()
        self._pan_start_offset = QPointF()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_background(self, pixmap: QPixmap | None):
        if pixmap is None or pixmap.isNull():
            self._bg_pixmap = None
        else:
            self._bg_pixmap = pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        self.update()

    def set_svg(self, data: QByteArray):
        self._renderer = QSvgRenderer(data)
        self.update()

    def set_zoom(self, factor: float):
        if factor == self._zoom:
            return
        self._zoom = factor
        self.update()

    def reset_view(self):
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self.update()

    # ---- Painting ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor("white"))

        # Centre the content, apply zoom, then apply the pan offset.
        p.save()
        p.translate(self.width() / 2 + self._offset.x(),
                    self.height() / 2 + self._offset.y())
        p.scale(self._zoom, self._zoom)
        p.translate(-self.width() / 2, -self.height() / 2)

        if self._bg_pixmap is not None:
            x = (self.width() - self._bg_pixmap.width()) / 2
            y = (self.height() - self._bg_pixmap.height()) / 2
            p.setOpacity(BACKGROUND_OPACITY)
            p.drawPixmap(int(x), int(y), self._bg_pixmap)
            p.setOpacity(1.0)

        if self._renderer is not None and self._renderer.isValid():
            self._renderer.render(p)

        p.restore()

    # ---- Right-drag panning ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.position()
            self._pan_start_offset = QPointF(self._offset)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._offset = self._pan_start_offset + delta
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)