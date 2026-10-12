# bezier_scene.py
from PySide6.QtCore import QRectF, Qt, Signal, QSize, QPointF
from PySide6.QtGui import QPen, QPixmap, QImage, QPainter, QColor
from PySide6.QtWidgets import (QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem)
from PySide6.QtSvg import QSvgRenderer

from scene.scene_io import generate_svg, save_state, load_state
from core.settings import ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH, DEFAULT_CURVE_COLOR, HOVER_TOLERANCE
from scene.link_manager import LinkManager
from scene.items.control_point import ControlPoint
from scene.items.bezier_curve import BezierCurve
from scene.shape_manager import ShapeManager
from scene.selection import Selection
from core.model import Document
from .transform_controller import TransformController
from .preset_controller import PresetController
from .model_registry import ModelRegistry
from .curve_builder import CurveBuilder
from scene.curve_renderer import CurveRenderer
from scene.point_renderer import PointRenderer

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    messageLogged = Signal(str)
    transformModeChanged = Signal(bool)
    presetStateChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.document = Document()


        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT
        self.viewbox = VIEWBOX_RECT

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
        #self.pending_curve = None
        self.mode = "create"
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selection = Selection(self)

        self.dragging_point = None
        self._ensuring_visible = False

        # ---- Background image ----
        self.background_item = None
        self.background_image_path = None
        self.background_pixmap = None

        # ---- Drag bookkeeping ----
        self._pending_collapse_point: ControlPoint | None = None
        self._drag_press_pos: QPointF | None = None
        self._drag_targets: dict[ControlPoint, QPointF] = {}
        self._drag_primary_start: QPointF | None = None

        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)

        # ---- Collaborators ----
        self.registry = ModelRegistry(self)
        self.curve_renderer = CurveRenderer(self)
        self.point_renderer = PointRenderer(self)
        self.link_manager = LinkManager(self)
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

    # ------------------------------------------------------------
    #  Public delegates (main_window / custom_view API)
    # ------------------------------------------------------------
    def start_rotation(self) -> bool:
        return self.transform.start_rotation()

    def start_scaling(self) -> bool:
        return self.transform.start_scaling()

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

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # A pending preset consumes this click, whatever the mode.
        if self.presets._pending is not None:
            keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.presets._place_preset(event.scenePos(), keep_armed=keep)
            return

        # ---- Create mode ----
        if self.mode == "create":
            self.builder.handle_click(event.scenePos())
            return

        # ---- Edit mode ----
        views = self.views()
        if not views:
            super().mousePressEvent(event)
            return
        item = self.itemAt(event.scenePos(), views[0].transform())

        if isinstance(item, ControlPoint) and item.curve.committed:
            if item not in self.selected_points:
                # Several points coincide at a junction, and itemAt returns the
                # topmost. If another curve's endpoint is stacked above the one
                # we selected, the click would land on it and collapse the
                # selection. Prefer a linked sibling that is already selected.
                group = self.link_manager.group_of(item) or ()
                item = next((pt for pt in group if pt in self.selected_points), item)
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if shift:
                self.toggle_selection(item)
                self.clear_hover()
                event.accept()
                return

            # Non-shift: selection collapses to exactly this point.
            # If the point is already part of a multi-point selection, defer
            # the collapse to release: a click collapses, a drag keeps the
            # whole selection and moves everything together.
            if item in self.selected_points and len(self.selected_points) > 1:
                self._pending_collapse_point = item
            else:
                self.set_selected_point(item)
                self._pending_collapse_point = None
            self._drag_press_pos = event.scenePos()

            self.clear_hover()
            self.dragging_point = item
            self._start_drag(item)
            super().mousePressEvent(event)
            return

        # Not on a point. Refresh hover for this exact scene position.
        self._update_hover(event.scenePos())
        if self.hovered_curve is not None:
            add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.select_curve_under_hover(add=add)
            event.accept()
            return

        self.set_selected_point(None)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

        if self._pending_collapse_point is not None and self._drag_press_pos is not None:
            press = self._drag_press_pos
            cur = event.scenePos()
            dx, dy = cur.x() - press.x(), cur.y() - press.y()
            if dx * dx + dy * dy > 25:  # ~5 px — real movement, not jitter
                self._pending_collapse_point = None

        if self.dragging_point is not None:
            delta = self.dragging_point.pos() - self._drag_primary_start
            for pt, start in self._drag_targets.items():
                pt.setPos(start + delta)
            self.link_manager.update_proximity(self.dragging_point)

        if self.dragging_point is None or self._ensuring_visible:
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
            if self.dragging_point is not None:
                pending = self._pending_collapse_point
                self._pending_collapse_point = None
                self._drag_press_pos = None
                self.dragging_point = None
                self._drag_targets = {}
                self._drag_primary_start = None
                self.link_manager.clear_proximity()

                if pending is not None:
                    self.set_selected_point(pending)

                self._update_hover(event.scenePos())
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Hover tracking
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        if self.transform.is_transforming():
            if self.transform.is_rotating():
                self.transform._update_rotation(scene_pos)
            else:
                self.transform._update_scaling(scene_pos)
            return
        if self.dragging_point is not None:
            return
        if self.mode == "create":
            return
        self._update_hover(scene_pos)

    def _update_hover(self, pos):
        new_hovered = None
        new_focused_pt = None

        if pos is not None:
            tol2 = HOVER_TOLERANCE * HOVER_TOLERANCE
            for curve in reversed(self.curves):
                if not curve.is_near(pos):
                    continue
                new_hovered = curve
                for pt in curve.points:
                    p = pt.pos()
                    dx, dy = p.x() - pos.x(), p.y() - pos.y()
                    if dx * dx + dy * dy <= tol2:
                        new_focused_pt = pt
                        break
                break

        self.selection.set_hover(new_hovered, new_focused_pt)

    def clear_hover(self):
        self.selection.clear_hover()

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

    def _propagate_move(self, source, pos):
        """Apply `pos` to every other point in source's link group.
        Base implementation reads from LinkManager directly."""
        group = self.link_manager.group_of(source)
        if group is None:
            return
        for pt in group:
            if pt is not source:
                pt.setPos(pos)

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
                for pt in curve.points:
                    if pt in sel.points:
                        sel.points.remove(pt)
                        pt.update()
                curve.update()
                self.messageLogged.emit(f"{curve.name} removed from selection")
            else:
                for pt in curve.points:
                    if pt not in sel.points:
                        sel.points.append(pt)
                    pt.update()
                curve.update()
                self.messageLogged.emit(f"Added {curve.name} to selection")
            return True

        # No shift: replace, unless this curve is already the whole selection.
        if in_selection and len(sel.points) == len(curve.points):
            self.clear_selection()
            self.messageLogged.emit(f"{curve.name} deselected")
            return True
        self.clear_selection()
        for pt in curve.points:
            sel.points.append(pt)
            pt.update()
        curve.update()
        self.messageLogged.emit(f"Selected {curve.name} ({len(curve.points)} points)")
        return True

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
    #  Drag helpers
    # ------------------------------------------------------------
    def _with_linked(self, points) -> set[ControlPoint]:
        """Return `points` plus every link-group sibling of any of them."""
        result = set(points)
        for pt in points:
            group = self.link_manager.group_of(pt)
            if group:
                result.update(group)
        return result

    def _start_drag(self, primary):
        primary_group = self._with_linked({primary})
        seeds = set(self.selected_points) | {primary}
        self._drag_targets = {pt: pt.pos()
                              for pt in self._with_linked(seeds) - primary_group}
        self._drag_primary_start = primary.pos()

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
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        BezierCurve._next_id = 1
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
        targets = self._with_linked(base_pts)
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
            self.transform._reanchor_transform()
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
        item.setPos(vb.center().x() - pw * scale / 2,
                    vb.center().y() - ph * scale / 2)

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
        targets = self._with_linked(self.selected_points)
        starts = {p: p.pos() for p in targets}
        for p, start in starts.items():
            p.setPos(start + offset)
        return True

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        if self.dragging_point is point:
            self.link_manager.update_proximity(point)

    def hide_hovered_curve_points(self) -> bool:
        if self.dragging_point is not None:
            return False  # don't hide a curve whose point is mid-drag
        if self.hovered_curve is None:
            return False
        self.hovered_curve.set_points_hidden(True)
        self.messageLogged.emit(f"Points hidden on {self.hovered_curve.name}")
        return True

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