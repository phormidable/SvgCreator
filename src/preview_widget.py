# preview_widget.py
"""PreviewWidget: a scrollable view of the current SVG, with a
semi-transparent background pixmap underneath.

Structure:
    PreviewWidget (QScrollArea)
        └── PreviewCanvas (QWidget, sized content_size × zoom)

The canvas paints both layers at its own size, so the background and
SVG always scale together. Right-drag pans by driving the scrollbars.
"""

from PySide6.QtWidgets import QWidget, QScrollArea, QToolBar, QComboBox, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QByteArray, QPointF, QSizeF, Signal
from PySide6.QtGui import QPainter, QPixmap, QColor
from PySide6.QtSvg import QSvgRenderer

from settings import ZOOM_LEVELS, PREVIEW_FIT_MARGIN, PREVIEW_WIDTH, PREVIEW_HEIGHT

BACKGROUND_OPACITY = 0.35
DEFAULT_CONTENT_SIZE = QSizeF(1024, 1024)


class PreviewCanvas(QWidget):
    """The scrollable content. Paints background + SVG at its own size.
    Emits pan_by(dx, dy) while right-dragging; the wrapper translates
    that into scrollbar moves."""

    pan_by = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        self._renderer: QSvgRenderer | None = None
        self._content_size = QSizeF(DEFAULT_CONTENT_SIZE)

        self._panning = False
        self._pan_start = QPointF()

    # ---- Content ----
    def set_background(self, pixmap: QPixmap | None):
        self._bg_pixmap = pixmap if pixmap and not pixmap.isNull() else None
        self.update()

    def set_svg(self, data: QByteArray):
        self._renderer = QSvgRenderer(data)
        if self._renderer.isValid():
            vb = self._renderer.viewBoxF()
            if not vb.isEmpty():
                self._content_size = vb.size()
        self.update()

    def content_size(self) -> QSizeF:
        return self._content_size

    # ---- Painting ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor("white"))

        if self._bg_pixmap is not None:
            scaled = self._bg_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.setOpacity(BACKGROUND_OPACITY)
            p.drawPixmap(x, y, scaled)
            p.setOpacity(1.0)

        if self._renderer is not None and self._renderer.isValid():
            self._renderer.render(p)

    # ---- Right-drag panning ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.pan_by.emit(-delta.x(), -delta.y())
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


class PreviewWidget(QWidget):
    """Container: a small toolbar on top, a scrollable canvas below.
    Owns its own zoom — independent from the drawing view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom = 1.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- Small toolbar ----
        self._toolbar = QToolBar()
        self._toolbar.setMovable(False)
        layout.addWidget(self._toolbar)

        self._zoom_combo = QComboBox()
        for label, factor in ZOOM_LEVELS:
            self._zoom_combo.addItem(label, factor)
        self._zoom_combo.setCurrentIndex(1)          # 1x
        self._zoom_combo.currentIndexChanged.connect(self._on_zoom_changed)

        self._toolbar.addWidget(QLabel(" Zoom: "))
        self._toolbar.addWidget(self._zoom_combo)

        reset_action = self._toolbar.addAction("↺ Reset")
        reset_action.setToolTip("Recenter the view")
        reset_action.triggered.connect(self.reset_view)

        # ---- Scrollable canvas ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("background-color: white;")

        self._canvas = PreviewCanvas(self._scroll)
        self._canvas.pan_by.connect(self._pan_by)
        self._scroll.setWidget(self._canvas)
        layout.addWidget(self._scroll, 1)

        self._update_canvas_size()

    # ---- Public API ----
    def set_background(self, pixmap):
        self._canvas.set_background(pixmap)

    def set_svg(self, data):
        self._canvas.set_svg(data)
        self._update_canvas_size()

    def set_zoom(self, factor):
        """Programmatic zoom. Updates the combo, which triggers the rebuild."""
        for i in range(self._zoom_combo.count()):
            if self._zoom_combo.itemData(i) == factor:
                self._zoom_combo.setCurrentIndex(i)
                return

    def reset_view(self):
        """Recenter: zoom back to 1x and reset scrollbars to top-left."""
        self._zoom_combo.setCurrentIndex(1)
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    # ---- Internal ----
    def _on_zoom_changed(self, index):
        self._zoom = self._zoom_combo.itemData(index)
        self._update_canvas_size()

    def _base_scale(self) -> float:
        """Scale that makes the viewBox fit inside the preview reference
        area at zoom = 1. Content-size-independent until set_svg runs."""
        cs = self._canvas.content_size()
        ref_w = PREVIEW_WIDTH - 4
        ref_h = PREVIEW_HEIGHT - PREVIEW_FIT_MARGIN
        return min(ref_w / cs.width(), ref_h / cs.height())

    def _update_canvas_size(self):
        cs = self._canvas.content_size()
        scale = self._base_scale() * self._zoom
        self._canvas.setFixedSize(
            max(1, int(cs.width() * scale)),
            max(1, int(cs.height() * scale)),
        )

    def _pan_by(self, dx, dy):
        h = self._scroll.horizontalScrollBar()
        v = self._scroll.verticalScrollBar()
        h.setValue(h.value() + int(dx))
        v.setValue(v.value() + int(dy))