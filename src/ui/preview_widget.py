# ui/preview_widget.py
"""PreviewWidget: a QGraphicsView showing the current SVG over an optional
background pixmap.

- The SVG is a QGraphicsSvgItem sharing a QSvgRenderer built from bytes.
- The background is a QGraphicsPixmapItem, scaled to the SVG's viewBox.
- Zoom is a view transform (base fit × user zoom); panning is ScrollHandDrag.
"""

from PySide6.QtCore import Qt, QByteArray, QRectF, Signal
from PySide6.QtGui import QPainter, QPixmap, QTransform
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import QComboBox, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel, QToolBar, QVBoxLayout, QWidget

from core.settings import PREVIEW_FIT_MARGIN, ZOOM_LEVELS

class PreviewWidget(QWidget):
    showSvgRequested = Signal()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_zoom()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = 1.0
        self._renderer: QSvgRenderer | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Toolbar ----
        self.bar = QToolBar()
        self.bar.setMovable(False)
        self.bar.addWidget(QLabel(" Zoom: "))
        self._zoom_combo = QComboBox()
        for label, factor in ZOOM_LEVELS:
            self._zoom_combo.addItem(label, factor)

        self._zoom_combo.setCurrentIndex(1)
        self._zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)
        self.bar.addWidget(self._zoom_combo)
        self.bar.addAction("↺ Reset").triggered.connect(self.reset_view)
        self.bar.addAction("📄 SVG code").triggered.connect(self.showSvgRequested.emit)
        outer.addWidget(self.bar)

        # ---- Scene: background item, then SVG item ----
        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(QRectF(0, 0, 1, 1))

        self._bg = QGraphicsPixmapItem()
        self._bg.setOpacity(0.35)
        self._bg.setZValue(-1)
        self._bg.setVisible(False)
        self._scene.addItem(self._bg)

        self._svg = QGraphicsSvgItem()
        self._svg.setZValue(0)
        self._scene.addItem(self._svg)

        # ---- View ----
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setBackgroundBrush(Qt.GlobalColor.white)
        self._view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self._view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        outer.addWidget(self._view, 1)

    # ------------------------------------------------------------
    #  Public API (same surface as before)
    # ------------------------------------------------------------
    def set_svg(self, data: QByteArray):
        self._renderer = QSvgRenderer(data)
        self._svg.setSharedRenderer(self._renderer)

        vb = self._renderer.viewBoxF()
        if vb.isEmpty():
            s = self._renderer.defaultSize()
            vb = QRectF(0, 0, s.width(), s.height())
        self._scene.setSceneRect(vb)
        self._svg.setPos(vb.topLeft())

        self._layout_background()
        self._apply_zoom()

    def set_background(self, pixmap: QPixmap | None):
        if pixmap is None or pixmap.isNull():
            self._bg.setVisible(False)
            return
        self._bg.setPixmap(pixmap)
        self._bg.setVisible(True)
        self._layout_background()

    def set_zoom(self, factor: float):
        for i in range(self._zoom_combo.count()):
            if self._zoom_combo.itemData(i) == factor:
                self._zoom_combo.setCurrentIndex(i)
                return

    def reset_view(self):
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentIndex(1)
        self._zoom_combo.blockSignals(False)
        self._zoom = 1.0
        self._apply_zoom()
        self._view.horizontalScrollBar().setValue(0)
        self._view.verticalScrollBar().setValue(0)

    # ------------------------------------------------------------
    #  Internal
    # ------------------------------------------------------------
    def _layout_background(self):
        pixmap = self._bg.pixmap()
        rect = self._scene.sceneRect()
        if pixmap.isNull() or rect.isEmpty():
            return
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(rect.width() / pw, rect.height() / ph)
        self._bg.setScale(scale)
        self._bg.setPos(rect.center().x() - pw * scale / 2, rect.center().y() - ph * scale / 2)

    def _apply_zoom(self):
        rect = self._scene.sceneRect()
        if rect.isEmpty():
            return
        vp = self._view.viewport().size()
        ref_w = vp.width()  - PREVIEW_FIT_MARGIN
        ref_h = vp.height() - PREVIEW_FIT_MARGIN
        if ref_w <= 0 or ref_h <= 0:
            return
        base = min(ref_w / rect.width(), ref_h / rect.height())
        anchor = self._view.mapToScene(self._view.viewport().rect().center())
        self._view.setTransform(QTransform().scale(base * self._zoom, base * self._zoom))
        self._view.centerOn(anchor)

    def _on_zoom_changed(self, index):
        factor = self._zoom_combo.itemData(index)
        if factor == self._zoom:
            return
        self._zoom = factor
        self._apply_zoom()