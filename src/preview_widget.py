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
from PySide6.QtCore import Qt, QByteArray, QPointF, QSizeF, Signal, QTimer
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
        """Recentre: zoom back to 1x and scroll to top-left."""
        # Block the combo signal so _on_zoom_changed does not fight us
        # by trying to preserve the current centre.
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentIndex(1)  # 1x index
        self._zoom_combo.blockSignals(False)
        self._zoom = 1.0
        self._update_canvas_size()
        self._scroll.horizontalScrollBar().setValue(0)
        self._scroll.verticalScrollBar().setValue(0)

    # ---- Internal ----
    def _on_zoom_changed(self, index):
        new_zoom = self._zoom_combo.itemData(index)
        if new_zoom == self._zoom:
            return
        norm = self._current_center_norm()
        self._zoom = new_zoom
        self._update_canvas_size()
        # Defer until Qt has updated the scroll ranges to match the new
        # canvas size; otherwise the viewport size we read is stale.
        QTimer.singleShot(0, lambda n=norm: self._center_on_norm(n))

    def _current_center_norm(self):
        """Return the viewport centre in canvas-normalized coords (0..1)."""
        canvas = self._canvas
        vp = self._scroll.viewport()

        if canvas.width() > vp.width():
            h = self._scroll.horizontalScrollBar()
            nx = (h.value() + vp.width() / 2) / canvas.width()
        else:
            nx = 0.5  # canvas fits; it is auto-centred via AlignCenter

        if canvas.height() > vp.height():
            v = self._scroll.verticalScrollBar()
            ny = (v.value() + vp.height() / 2) / canvas.height()
        else:
            ny = 0.5

        return (nx, ny)

    def _center_on_norm(self, norm):
        nx, ny = norm
        canvas = self._canvas
        vp = self._scroll.viewport()
        h = self._scroll.horizontalScrollBar()
        v = self._scroll.verticalScrollBar()

        if canvas.width() > vp.width():
            h.setValue(int(nx * canvas.width() - vp.width() / 2))
        else:
            h.setValue(0)

        if canvas.height() > vp.height():
            v.setValue(int(ny * canvas.height() - vp.height() / 2))
        else:
            v.setValue(0)

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