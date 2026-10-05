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

        if self._bg_pixmap is not None:
            x = (self.width() - self._bg_pixmap.width()) // 2
            y = (self.height() - self._bg_pixmap.height()) // 2
            p.setOpacity(BACKGROUND_OPACITY)
            p.drawPixmap(x, y, self._bg_pixmap)
            p.setOpacity(1.0)

        if self._renderer is not None and self._renderer.isValid():
            self._renderer.render(p)