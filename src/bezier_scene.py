# bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QDialog, QPushButton,  QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtSvg import QSvgRenderer

from settings import (ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR,
    VIEWBOX_BORDER_WIDTH, SVG_STROKE_COLOR, SVG_STROKE_WIDTH, SVG_FILL, HOVER_TOLERANCE)

from control_point import ControlPoint
from bezier_curve import BezierCurve

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()
    curveListChanged = Signal()
    curveSelected = Signal(int)
    curveDragFinished = Signal()

    def __init__(self):
        super().__init__()

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT   # full working area (scene rect)
        self.viewbox = VIEWBOX_RECT     # region that gets exported

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        self.pending_curve = None     # BezierCurve currently being placed
        self.mode = "create"
        self.selected_curve_idx = -1
        self.dragging_curve = None
        self._hovered_curve = None
        self._ensuring_visible = False
        self.background_item = None
        self.selected_point = None
        self.background_image_path = None

        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            views = self.views()
            if not views:
                super().mousePressEvent(event)
                return
            item = self.itemAt(event.scenePos(), self.views()[0].transform())

            if isinstance(item, ControlPoint):
                curve = item.curve
                if curve.committed:
                    shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

                    # Shift+click on a *different* point while one is selected
                    # → ask the user how to link them.
                    if shift and self.selected_point is not None and self.selected_point is not item:
                        self._prompt_link(self.selected_point, item)
                        event.accept()
                        return

                    # Normal click: make this the selected point (deselect the previous one).
                    self._set_selected_point(item)

                    # Existing drag setup, unchanged.
                    self._clear_hover()
                    self.dragging_curve = curve
                    curve.set_highlighted(True)
                    idx = self.curves.index(curve)
                    if idx != self.selected_curve_idx:
                        self.selected_curve_idx = idx
                        self.curveSelected.emit(idx)
                super().mousePressEvent(event)
                return

            if self.mode == "create":
                if self.pending_curve is None:
                    self.pending_curve = BezierCurve(self)
                self.pending_curve.add_point(event.scenePos())
                if self.pending_curve.is_complete():
                    self.finalize_curve()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.dragging_curve is None or self._ensuring_visible:
            return
        self._ensuring_visible = True
        try:
            pos = event.scenePos()
            target = QRectF(pos.x() - 1, pos.y() - 1, 2, 2)
            for view in self.views():
                view.ensureVisible(target, 60, 60)
        finally:
            self._ensuring_visible = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging_curve is not None:
                self.dragging_curve.set_highlighted(False)
                self.dragging_curve = None
                self._update_hover(event.scenePos())
                self.curveDragFinished.emit()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Hover tracking
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        """Called by the view's mouseMoved signal (scene_pos or None)."""
        if self.dragging_curve is not None:
            return
        self._update_hover(scene_pos)

    def _update_hover(self, pos):
        new_hovered = None
        if pos is not None:
            for curve in reversed(self.curves):
                if curve.is_near(pos, HOVER_TOLERANCE):
                    new_hovered = curve
                    break
        if new_hovered is self._hovered_curve:
            return
        if self._hovered_curve is not None:
            self._hovered_curve.set_hovered(False)
        self._hovered_curve = new_hovered
        if new_hovered is not None:
            new_hovered.set_hovered(True)

    def _clear_hover(self):
        if self._hovered_curve is not None:
            self._hovered_curve.set_hovered(False)
            self._hovered_curve = None

    def _set_selected_point(self, point):
        if self.selected_point is point:
            return
        if self.selected_point is not None:
            self.selected_point.set_selected(False)
        self.selected_point = point
        if point is not None:
            point.set_selected(True)

    def _prompt_link(self, point_a, point_b):
        parent = self.views()[0] if self.views() else None

        dialog = QDialog(parent)
        dialog.setWindowTitle("Link Points")

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Do you want to link these 2 points?"))

        info = QLabel(
            f"1st: ({point_a.pos().x():.2f}, {point_a.pos().y():.2f})\n"
            f"2nd: ({point_b.pos().x():.2f}, {point_b.pos().y():.2f})"
        )
        info.setStyleSheet("color: #555;")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        btn_1st = QPushButton("Yes, 1st")
        btn_2nd = QPushButton("Yes, 2nd")
        btn_no = QPushButton("No")
        btn_row.addWidget(btn_1st)
        btn_row.addWidget(btn_2nd)
        btn_row.addWidget(btn_no)
        layout.addLayout(btn_row)

        # Default to "No" so Enter doesn't accidentally apply a link.
        btn_no.setDefault(True)

        choice = {"value": None}

        def pick(v):
            choice["value"] = v
            dialog.accept()

        btn_1st.clicked.connect(lambda: pick("1st"))
        btn_2nd.clicked.connect(lambda: pick("2nd"))
        btn_no.clicked.connect(lambda: pick("no"))

        dialog.exec()

        if choice["value"] == "1st":
            point_b.setPos(point_a.pos())
        elif choice["value"] == "2nd":
            point_a.setPos(point_b.pos())
        # "no" or closed → nothing

        self._set_selected_point(None)

    # ------------------------------------------------------------
    #  Curve finalization
    # ------------------------------------------------------------
    def finalize_curve(self):
        curve = self.pending_curve
        self.pending_curve = None
        curve.committed = True
        for pt in curve.points:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        curve.rebuild_path()
        self.curves.append(curve)
        self.selected_curve_idx = len(self.curves) - 1
        self.emit_svg()
        self.curveListChanged.emit()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Change notification from a curve
    # ------------------------------------------------------------
    def on_curve_changed(self):
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  SVG generation — viewBox is simply self.viewbox
    # ------------------------------------------------------------
    def generate_svg(self):
        path_commands = []
        for curve in self.curves:
            d = curve.svg_path_string()
            if d:
                path_commands.append(d)

        vb = self.viewbox
        header = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{vb.x():.2f} {vb.y():.2f} '
            f'{vb.width():.2f} {vb.height():.2f}" '
            f'width="{vb.width():.2f}" height="{vb.height():.2f}">'
        )

        if not path_commands:
            return header + '</svg>'

        d_string = " ".join(path_commands)
        return (
            header
            + f'<path d="{d_string}" fill="{SVG_FILL}" '
              f'stroke="{SVG_STROKE_COLOR}" '
              f'stroke-width="{SVG_STROKE_WIDTH}"/>'
              '</svg>'
        )

    def emit_svg(self):
        self.svgCodeChanged.emit(self.generate_svg())

    # ------------------------------------------------------------
    #  Discard incomplete curve
    # ------------------------------------------------------------
    def discard_current_points(self):
        if self.pending_curve is None:
            return
        self.pending_curve.dispose()
        self.pending_curve = None
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        self._clear_hover()
        self.selected_point = None
        if self.pending_curve is not None:
            self.pending_curve.dispose()
            self.pending_curve = None
        for curve in self.curves:
            curve.dispose()
        self.curves.clear()

        self.selected_curve_idx = -1
        BezierCurve._next_id = 1 # c'est mieux de repartir à 1.
        self.dragging_curve = None

        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()
        self._remove_background_image()

    # ------------------------------------------------------------
    #  Save and Load
    # ------------------------------------------------------------
    def save_state(self) -> dict:
        state = {
            "version": 1,
            "curves": [
                [[round(p.x(), 3), round(p.y(), 3)] for p in curve.points]
                for curve in self.curves
            ],
        }
        if self.background_image_path:
            state["background"] = self.background_image_path
        return state

    def load_state(self, state: dict):
        curves_data = state.get("curves", [])

        self.blockSignals(True)
        try:
            self.clear_all()
            for points_data in curves_data:
                curve = self._build_curve_from_points(points_data)
                self.curves.append(curve)
            self.selected_curve_idx = len(self.curves) - 1 if self.curves else -1

            bg = state.get("background")
            if bg:
                self.load_background_image(bg)
        finally:
            self.blockSignals(False)

        # Manually notify listeners now that the batch rebuild is done.
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()

    def _build_curve_from_points(self, points_data) -> BezierCurve:
        if not isinstance(points_data, list) or len(points_data) != 4:
            raise ValueError(f"Expected 4 points per curve, got {points_data!r}")
        curve = BezierCurve(self)
        curve.committed = True
        for i, coords in enumerate(points_data):
            try:
                x, y = float(coords[0]), float(coords[1])
            except (TypeError, IndexError, ValueError):
                raise ValueError(f"Invalid point #{i}: {coords!r}")
            curve.add_point(QPointF(x, y))
        curve.rebuild_path()
        return curve

    # ------------------------------------------------------------
    #  Background image
    # ------------------------------------------------------------
    def load_background_image(self, filepath):
        pixmap = self._read_image(filepath)
        if pixmap is None:
            return False

        self._remove_background_image()
        self.background_image_path = filepath

        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.35)
        item.setZValue(-50)  # above viewbox (-100), below curves (-1)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)  # click-through
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Scale to fit inside the viewbox, preserve aspect ratio, center it.
        vb = self.viewbox
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(vb.width() / pw, vb.height() / ph)
        item.setScale(scale)
        item.setPos(vb.center().x() - pw * scale / 2,
                    vb.center().y() - ph * scale / 2)

        self.addItem(item)
        self.background_item = item
        print(f"scale = {scale}")
        return True

    def _remove_background_image(self):
        if self.background_item is not None:
            self.removeItem(self.background_item)
            self.background_item = None
            self.background_image_path = None

    def _read_image(self, filepath):
        """Load a raster or SVG file into a QPixmap (or None on failure)."""
        if filepath.lower().endswith(".svg"):
            renderer = QSvgRenderer(filepath)
            if not renderer.isValid():
                return None
            # Render at a resolution well above the viewbox so zooming stays crisp.
            size = renderer.defaultSize()
            target = int(max(self.viewbox.width(), self.viewbox.height()) * 2)
            if size.isEmpty():
                size = QSize(target, target)
            else:
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

    # ------------------------------------------------------------
    #  Access to curves for info panel
    # ------------------------------------------------------------
    def get_curve_points(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            return self.curves[curve_idx].points
        return None

    def move_selected_point(self, curve_idx, point_idx, pos):
        if 0 <= curve_idx < len(self.curves):
            self.curves[curve_idx].move_point(point_idx, pos)