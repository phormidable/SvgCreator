# scene/background_image.py
"""BackgroundImage: the optional reference image drawn behind the curves.

Owns the QGraphicsPixmapItem, the source file path, and the cached pixmap.
Raster files load directly; SVG files are rendered to a QImage first. The
pixmap is scaled to fit the viewbox and centred on it.

Reads through `self.scene`: viewbox, messageLogged, addItem / removeItem.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem


class BackgroundImage:
    def __init__(self, scene):
        self.scene = scene
        self.item: QGraphicsPixmapItem | None = None
        self.path: str | None = None
        self.pixmap: QPixmap | None = None

    # ------------------------------------------------------------
    #  Load / remove
    # ------------------------------------------------------------
    def load(self, filepath: str) -> bool:
        pixmap = self._read(filepath)
        if pixmap is None:
            return False

        self.remove()
        self.path = filepath
        self.pixmap = pixmap

        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.35)
        item.setZValue(-50)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        vb = self.scene.viewbox
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(vb.width() / pw, vb.height() / ph)
        item.setScale(scale)
        item.setPos(vb.center().x() - pw * scale / 2,
                    vb.center().y() - ph * scale / 2)

        self.scene.addItem(item)
        self.item = item
        self.scene.messageLogged.emit(f"Background loaded: {filepath}")
        return True

    def remove(self):
        if self.item is None:
            return
        self.scene.removeItem(self.item)
        self.item = None
        self.path = None
        self.pixmap = None

    # ------------------------------------------------------------
    #  Image loading
    # ------------------------------------------------------------
    def _read(self, filepath: str) -> QPixmap | None:
        """Load a raster or SVG file into a QPixmap (or None on failure)."""
        if filepath.lower().endswith(".svg"):
            renderer = QSvgRenderer(filepath)
            if not renderer.isValid():
                return None

            target = int(max(self.scene.viewbox.width(),
                             self.scene.viewbox.height()) * 2)
            size = renderer.defaultSize()
            if size.isEmpty():
                size = renderer.viewBoxF().size().toSize()
            if size.isEmpty():
                size = QSize(target, target)

            scale = target / max(size.width(), size.height())
            size = QSize(int(size.width() * scale), int(size.height() * scale))

            image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            return QPixmap.fromImage(image)

        pixmap = QPixmap(filepath)
        return pixmap if not pixmap.isNull() else None

    def refit(self):
        """Re-scale and re-centre the background to fit the current viewbox.
        Called after the viewbox is resized."""
        if self.item is None or self.pixmap is None:
            return
        pw, ph = self.pixmap.width(), self.pixmap.height()
        vb = self.scene.viewbox
        scale = min(vb.width() / pw, vb.height() / ph)
        self.item.setScale(scale)
        self.item.setPos(vb.center().x() - pw * scale / 2,
                         vb.center().y() - ph * scale / 2)