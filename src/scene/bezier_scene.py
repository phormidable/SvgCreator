# scene/bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter, QColor
from PySide6.QtWidgets import (QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem)
from PySide6.QtSvg import QSvgRenderer

from .scene_io import generate_svg, save_state, load_state
from core.settings import ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH, DEFAULT_CURVE_COLOR, HOVER_TOLERANCE
from .link_manager import LinkManager
from .items.bezier_curve import BezierCurve
from .shape_manager import ShapeManager
from .selection import Selection
from core.model import Document
from .transform_controller import TransformController
from .preset_controller import PresetController
from .model_registry import ModelRegistry
from .curve_builder import CurveBuilder
from .curve_renderer import CurveRenderer
from .point_renderer import PointRenderer
from .items.grid_item import GridItem
from core.settings import GRID_DEFAULT_SPACING
from .curve_geometry import curve_bbox
from .mouse_controller import MouseController
class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    messageLogged = Signal(str)
    transformModeChanged = Signal(bool)
    presetStateChanged = Signal(str)
    hoveredPointChanged = Signal(object)  # ControlPoint | None
    transformTypedChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.document = Document()

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT
        self.viewbox = VIEWBOX_RECT

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        self.mode = "create"
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selection = Selection(self)




        # ---- Background image ----
        self.background_item = None
        self.background_image_path = None
        self.background_pixmap = None



        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)

        self.grid_item = GridItem(self.artboard, GRID_DEFAULT_SPACING)
        self.grid_item.setVisible(False)  # MainWindow turns it on at startup
        self.addItem(self.grid_item)


        # ---- Collaborators ----
        self.registry = ModelRegistry(self)
        self.curve_renderer = CurveRenderer(self)
        self.point_renderer = PointRenderer(self)
        self.link_manager = LinkManager(self)
        self.mouse = MouseController(self)
        self.shape_manager = ShapeManager(self)
        self.transform = TransformController(self)
        self.presets = PresetController(self)
        self.builder = CurveBuilder(self)


    # ------------------------------------------------------------
    #  Read-only views on Selection
    # ------------------------------------------------------------
    @property
    def selected_points(self):
        return self.selection.points

    @property
    def hovered_curve(self):
        return self.selection.hovered_curve

    @property
    def focused_point(self):
        return self.selection.focused_point

    @property
    def pending_curve(self):
        return self.builder.pending_curve

    @property
    def dragging_point(self):
        return self.mouse.dragging_point

    @dragging_point.setter
    def dragging_point(self, value):
        self.mouse.dragging_point = value

    # ------------------------------------------------------------
    #  Public delegates (main_window / custom_view API)
    # ------------------------------------------------------------
    def start_rotation(self) -> bool:
        return self.transform.start_rotation()

    def start_scaling(self) -> bool:
        return self.transform.start_scaling()

    def start_move(self) -> bool:
        return self.transform.start_move()

    def end_transform(self, commit: bool = True):
        return self.transform.end_transform(commit)

    def is_transforming(self) -> bool:
        return self.transform.is_transforming()

    def arm_preset(self, name: str) -> bool:
        return self.presets.arm_preset(name)

    def cancel_preset(self) -> bool:
        return self.presets.cancel_preset()

    def on_shift_released(self):
        return self.presets.on_shift_released()

    def ui_curves(self, shape):
        return self.registry.ui_curves(shape)

    def set_degree(self, degree: int):
        self.builder.set_degree(degree)

    def discard_current_points(self):
        self.builder.discard()

    def cancel_pending_curve(self) -> bool:
        return self.builder.cancel_pending_curve()

    def set_grid_visible(self, visible: bool):
        self.grid_item.setVisible(visible)

    def set_grid_spacing(self, spacing: int):
        self.grid_item.set_spacing(spacing)

    def set_snap_enabled(self, enabled: bool):
        self.grid_item.set_snap_enabled(enabled)

    def handle_transform_key(self, event) -> bool:
        return self.transform.handle_key(event)

    def mousePressEvent(self, event):
        if self.mouse.mouse_press(event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.mouse.mouse_move(event):
            super().mouseMoveEvent(event)
        self.mouse.post_mouse_move(event)

    def mouseReleaseEvent(self, event):
        if self.mouse.mouse_release(event):
            super().mouseReleaseEvent(event)

    def on_mouse_moved(self, scene_pos):
        self.mouse.on_mouse_moved(scene_pos)

    def clear_hover(self):
        self.mouse.clear_hover()

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        self.mouse.on_point_moved(point)
    # ------------------------------------------------------------
    #  Selection
    # ------------------------------------------------------------
    def set_selected_point(self, point):
        """Replace the whole selection with just `point` (or clear if None)."""
        if point is None:
            self.clear_selection()
            return
        if len(self.selection.points) == 1 and self.selection.points[0] is point:
            return
        self.clear_selection()
        self.selection.set_point(point)

    def toggle_selection(self, point):
        self.selection.toggle_point(point)

    def clear_selection(self):
        self.selection.clear_points()
        self.selection.select_shape(None)

    def select_curve_under_hover(self, add: bool = False) -> bool:
        """Toggle selection of the hovered curve. With `add`, the curve joins
        the existing selection instead of replacing it. Returns True if handled."""
        if self.hovered_curve is None:
            return False
        curve = self.hovered_curve
        sel = self.selection
        in_selection = sel.is_curve_selected(curve)

        if add:
            if in_selection:
                sel.remove_points(curve.points)
                self.messageLogged.emit(f"{curve.name} removed from selection")
            else:
                sel.add_points(curve.points)
                self.messageLogged.emit(f"Added {curve.name} to selection")
            return True

        # No shift: replace, unless this curve is already the whole selection.
        if in_selection and len(sel.points) == len(curve.points):
            self.clear_selection()
            self.messageLogged.emit(f"{curve.name} deselected")
            return True
        self.clear_selection()
        sel.add_points(curve.points)
        self.messageLogged.emit(f"Selected {curve.name} ({len(curve.points)} points)")
        return True

    def select_in_rect(self, rect: QRectF, add: bool = False) -> int:
        """Select every visible control point whose position lies inside
        `rect` (scene coordinates). With `add`, keeps the existing selection."""
        if not add:
            self.clear_selection()
        selected = self.selection.points
        to_add = []
        for curve in self.curves:
            if curve.points_hidden:
                continue
            for pt in curve.points:
                if pt in selected:
                    continue
                if rect.contains(pt.model_pos()):
                    to_add.append(pt)
        self.selection.add_points(to_add)
        if to_add:
            self.messageLogged.emit(f"Selected {len(to_add)} point(s)")
        return len(to_add)

    def set_curve_color(self, color):
        self.curve_color = QColor(color)
        for curve in self.curves:
            curve.set_color(self.curve_color)
        if self.pending_curve is not None:
            self.pending_curve.set_color(self.curve_color)
        self.shape_manager.apply_curve_colors()

    # ------------------------------------------------------------
    #  Degree, curve finalization, change notification
    # ------------------------------------------------------------

    def on_curve_changed(self):
        self.emit_svg()
        self.shape_manager.update_fills()



    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        self.clear_hover()
        self.transform.end_transform(commit=False)
        self.set_selected_point(None)
        self.builder.clear()

        while self.curves:
            self.curves.pop().dispose()
        self.curves.clear()
        self.registry.reset()  # ← new
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)

        BezierCurve._next_id = 1
        from core.model import Point, Junction, Curve, Shape, Chain
        Point._next_id = 1
        Junction._next_id = 1
        Curve._next_id = 1
        Shape._next_id = 1
        Chain._next_id = 1
        self.dragging_point = None
        self._remove_background_image()
        self.emit_svg()
        self.link_manager.reset()
        self.shape_manager.reset()
        self.messageLogged.emit("Scene cleared")

    # ------------------------------------------------------------
    #  Save / load / SVG
    # ------------------------------------------------------------
    def generate_svg(self, bordered: bool = False):
        return generate_svg(self, bordered=bordered)

    def emit_svg(self):
        # Preview mirrors the drawing area, so it always uses borders.
        self.svgCodeChanged.emit(generate_svg(self, bordered=True))

    def save_state(self) -> dict:
        return save_state(self)

    def load_state(self, state: dict):
        load_state(self, state)

    # ------------------------------------------------------------
    #  Mirror
    # ------------------------------------------------------------
    def mirror_selection(self, axis: str) -> bool:
        """Reflect the selection across the horizontal line (axis='x') or
        vertical line (axis='y') through the barycentre of its points."""
        if not self.selected_points:
            self.messageLogged.emit(
                "Nothing to mirror — select a curve (A or click) or a shape (S) first")
            return False

        base_pts = set(self.selected_points)
        px = sum(p.pos().x() for p in base_pts) / len(base_pts)
        py = sum(p.pos().y() for p in base_pts) / len(base_pts)

        # Include linked siblings so they stay coincident.
        targets = self.link_manager.with_linked(base_pts)
        starts = {p: p.pos() for p in targets}
        if axis == "x":
            for p, start in starts.items():
                p.setPos(start.x(), 2 * py - start.y())
        else:
            for p, start in starts.items():
                p.setPos(2 * px - start.x(), start.y())

        self.messageLogged.emit(
            f"Mirrored across {axis.upper()} axis around ({px:.1f}, {py:.1f})")
        if self.transform.is_transforming():
            self.transform.reanchor_transform()
        return True

    def center_selection(self, axis: str) -> bool:
        if not self.selected_points:
            self.messageLogged.emit(
                "Nothing to centre — select a curve (A or click) or a shape (S) first")
            return False

        bbox = self.selection_curve_bbox()
        if bbox is None:
            return False
        min_x, min_y, max_x, max_y = bbox

        targets = self.link_manager.with_linked(set(self.selected_points))
        starts = {p: p.pos() for p in targets}

        center = self.viewbox.center()
        if axis == "horizontal":
            offset = center.x() - (min_x + max_x) / 2
            for p, start in starts.items():
                p.setPos(start.x() + offset, start.y())
            self.messageLogged.emit(f"Centred horizontally on x={center.x():.1f}")
        elif axis == "vertical":
            offset = center.y() - (min_y + max_y) / 2
            for p, start in starts.items():
                p.setPos(start.x(), start.y() + offset)
            self.messageLogged.emit(f"Centred vertically on y={center.y():.1f}")
        else:
            return False

        if self.transform.is_transforming():
            self.transform.reanchor_transform()
        return True

    # ------------------------------------------------------------
    #  Background image
    # ------------------------------------------------------------
    def load_background_image(self, filepath):
        pixmap = self._read_image(filepath)
        if pixmap is None:
            return False

        self._remove_background_image()
        self.background_image_path = filepath
        self.background_pixmap = pixmap

        item = QGraphicsPixmapItem(pixmap)
        item.setOpacity(0.35)
        item.setZValue(-50)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        vb = self.viewbox
        pw, ph = pixmap.width(), pixmap.height()
        scale = min(vb.width() / pw, vb.height() / ph)
        item.setScale(scale)
        item.setPos(vb.center().x() - pw * scale / 2, vb.center().y() - ph * scale / 2)

        self.addItem(item)
        self.background_item = item
        self.messageLogged.emit(f"Background loaded: {filepath}")
        return True

    def _remove_background_image(self):
        if self.background_item is not None:
            self.removeItem(self.background_item)
            self.background_item = None
            self.background_image_path = None
            self.background_pixmap = None

    def _read_image(self, filepath):
        """Load a raster or SVG file into a QPixmap (or None on failure)."""
        if filepath.lower().endswith(".svg"):
            renderer = QSvgRenderer(filepath)
            if not renderer.isValid():
                return None

            target = int(max(self.viewbox.width(), self.viewbox.height()) * 2)
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

    # ------------------------------------------------------------
    #  Point movement
    # ------------------------------------------------------------
    def move_selected_points(self, dx: float, dy: float) -> bool:
        if not self.selected_points:
            return False
        offset = QPointF(dx, dy)
        targets = self.link_manager.with_linked(self.selected_points)
        starts = {p: p.model_pos() for p in targets}
        for p, start in starts.items():
            p.setPos(start + offset)
        # The mouse hasn't moved and the hovered point is unchanged, so nothing
        # downstream refreshes the tooltip. Re-emit so it picks up the new position.
        if self.focused_point is not None:
            self.hoveredPointChanged.emit(self.focused_point)
        return True


    def hide_points(self) -> bool:
        """Hide the control points of every curve that has a point in the
        selection. Falls back to the hovered curve when nothing is selected."""
        if self.dragging_point is not None:
            return False  # don't yank points out from under an active drag

        curves = {pt.curve for pt in self.selected_points if pt.curve is not None}
        if not curves and self.hovered_curve is not None:
            curves = {self.hovered_curve}
        if not curves:
            self.messageLogged.emit("Nothing to hide — hover a curve or select points first")
            return False

        n = sum(1 for c in curves if not c.points_hidden)
        for c in curves:
            c.set_points_hidden(True)
        if n:
            self.messageLogged.emit(f"Points hidden on {n} curve(s)")
        return n > 0

    def show_all_points(self) -> int:
        n = 0
        for curve in self.curves:
            if curve.points_hidden:
                curve.set_points_hidden(False)
                n += 1
        if n:
            self.messageLogged.emit(f"Restored points on {n} curve(s)")
        return n

    # ------------------------------------------------------------
    #  Delete selection
    # ------------------------------------------------------------
    def delete_selection(self) -> int:
        """Delete every curve selected directly (curve_selected) or via a
        selected shape. Returns the number of curves removed."""
        to_delete: set[BezierCurve] = set()
        for curve in self.curves:
            if curve.curve_selected:
                to_delete.add(curve)
        for shape in self.selection.selected_shapes():
            to_delete.update(self.ui_curves(shape))

        if not to_delete:
            self.messageLogged.emit("Nothing selected to delete")
            return 0

        self.clear_hover()
        self.selection.select_shape(None)

        curves = list(to_delete)
        for curve in curves:
            self.curves.remove(curve)
            for pt in curve.points:
                if pt in self.selected_points:
                    self.selected_points.remove(pt)
                pt.update()

        for curve in curves:
            curve.dispose()

        self.shape_manager.refresh()
        self.emit_svg()
        n = len(curves)
        self.messageLogged.emit(
            f"Deleted {curves[0].name}" if n == 1 else f"Deleted {n} curves")
        return n

    def snap_selection_to_grid(self) -> int:
        """Snap every selected point (plus its linked siblings) to the nearest
        grid line. Uses the current spacing regardless of the snap toggle —
        the caller has explicitly asked for it. Returns the number of points
        whose position actually changed."""
        if not self.selected_points:
            return 0
        targets = self.link_manager.with_linked(self.selected_points)
        n = 0
        for pt in targets:
            start = pt.model_pos()
            snapped = self.grid_item.snap_to(start)
            if snapped != start:
                pt.setPos(snapped)
                n += 1
        return n

    def selection_curve_bbox(self):
        """Tight bbox (min_x, min_y, max_x, max_y) of the actual curve geometry
        for every curve touched by the selection. None if no curve is involved.
        Unlike a control-polygon bbox, this ignores handles that wander away
        from the curve."""
        curves = {pt.curve for pt in self.selected_points if pt.curve is not None}
        if not curves:
            return None

        boxes = []
        for curve in curves:
            pts = [(p.model_pos().x(), p.model_pos().y()) for p in curve.points]
            boxes.append(curve_bbox(pts, curve.degree))

        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))