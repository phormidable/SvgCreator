# preview_widget.py
"""PreviewWidget: paints a background pixmap (semi-transparent, centred)
then renders the current SVG on top. Single widget, one paint event, no
sibling transparency to worry about."""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QPainter, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer

BACKGROUND_OPACITY = 0.35


class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        self._renderer: QSvgRenderer | None = None
        self._zoom = 1.0

    def set_zoom(self, factor: float):
        if factor == self._zoom:
            return
        self._zoom = factor
        self.update()

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

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor("white"))

        p.save()
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(self._zoom, self._zoom)
        p.translate(-self.width() / 2, -self.height() / 2)

        if self._bg_pixmap is not None:
            x = (self.width() - self._bg_pixmap.width()) // 2
            y = (self.height() - self._bg_pixmap.height()) // 2
            p.setOpacity(BACKGROUND_OPACITY)
            p.drawPixmap(x, y, self._bg_pixmap)
            p.setOpacity(1.0)

        if self._renderer is not None and self._renderer.isValid():
            self._renderer.render(p)

        p.restore()