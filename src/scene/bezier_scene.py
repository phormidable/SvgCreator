# scene/bezier_scene.py
from PySide6.QtCore import Signal, QRectF, QTimer
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (QGraphicsScene, QGraphicsRectItem)

from .scene_io import generate_svg, load_state
from core.settings import (ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR,
                           VIEWBOX_BORDER_WIDTH, DEFAULT_CURVE_COLOR, GRID_DEFAULT_SPACING, STROKE_DEFAULT_WIDTH)
from core.model import Document
from scene.managers_controllers.link_manager import LinkManager
from .items.bezier_curve import BezierCurve
from .items.snap_indicator import SnapIndicator
from .items.grid_item import GridItem
from scene.managers_controllers.shape_manager import ShapeManager
from .selection import Selection
from scene.managers_controllers.transform_controller import TransformController
from scene.managers_controllers.preset_controller import PresetController
from .model_registry import ModelRegistry
from .curve_builder import CurveBuilder
from .curve_renderer import CurveRenderer
from .point_renderer import PointRenderer
from scene.managers_controllers.mouse_controller import MouseController
from .selection_ops import SelectionOps
from .background_image import BackgroundImage
from .items.origin_marker import OriginMarker
from .clipboard import Clipboard
from scene.managers_controllers.undo_manager import UndoManager


class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    messageLogged = Signal(str)
    transformModeChanged = Signal(bool)
    presetStateChanged = Signal(str)
    hoveredPointChanged = Signal(object)  # ControlPoint | None
    transformTypedChanged = Signal(str)
    undoStateChanged = Signal()

    def __init__(self):
        super().__init__()
        self.document = Document()

        # ---- Static geometry ----
        self.artboard = ARTBOARD_RECT
        self.viewbox = VIEWBOX_RECT
        self.stroke_width = STROKE_DEFAULT_WIDTH   # NEW: configurable stroke width

        # ---- State ----
        self.curves = []    # committed BezierCurve objects
        self.mode = "create"
        self.curve_color = QColor(DEFAULT_CURVE_COLOR)
        self.selection = Selection(self)

        self.background = BackgroundImage(self)

        # ---- Scene rect = artboard, never changes during editing ----
        self.setSceneRect(self.artboard)

        # ---- Viewbox rectangle: white, sits under everything ----
        self.viewbox_item = QGraphicsRectItem(self.viewbox)
        self.viewbox_item.setBrush(VIEWBOX_BACKGROUND_COLOR)
        self.viewbox_item.setPen(QPen(VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH))
        self.viewbox_item.setZValue(-100)
        self.addItem(self.viewbox_item)

        self.origin_marker = OriginMarker()
        self.addItem(self.origin_marker)

        self.grid_item = GridItem(self.artboard, GRID_DEFAULT_SPACING)
        self.grid_item.setVisible(False)  # MainWindow turns it on at startup
        self.addItem(self.grid_item)

        self.snap_indicator = SnapIndicator()
        self.addItem(self.snap_indicator)

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
        self.selection_ops = SelectionOps(self)
        self.clipboard = Clipboard(self)
        self.undo = UndoManager(self)

        # NEW: Auto-update topology when the Document changes
        self.document.curve_added.connect(self.shape_manager.refresh)
        self.document.curve_deleted.connect(self.shape_manager.refresh)

        # NEW: React to point movement and linking changes
        self.document.points_linked.connect(self._on_points_linked)
        self.document.points_unlinked.connect(self._on_points_unlinked)

        # ---- NEW: Debounce timer for heavy updates during drags ----
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(100)  # 100ms debounce
        self._update_timer.timeout.connect(self._apply_pending_updates)
        self._pending_svg = False
        self._pending_fills = False

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

    @property
    def background_image_path(self):
        return self.background.path

    @property
    def background_pixmap(self):
        return self.background.pixmap

    # ------------------------------------------------------------
    #  Public delegates (main_window / custom_view API)
    # ------------------------------------------------------------

    def load_background_image(self, filepath):
        return self.background.load(filepath)

    def end_transform(self, commit: bool = True):
        return self.transform.end_transform(commit)

    def is_transforming(self) -> bool:
        return self.transform.is_transforming()

    def ui_curves(self, shape):
        return self.registry.ui_curves(shape)

    def set_snap_enabled(self, enabled: bool):
        self.grid_item.set_snap_enabled(enabled)
        if not enabled:
            self.snap_indicator.hide_indicator()

    def set_selected_point(self, point):
        self.selection.set_point(point)

    def clear_selection(self):
        self.selection.clear()

    def select_curve_under_hover(self, add: bool = False) -> bool:
        return self.selection_ops.select_curve_under_hover(add=add)

    # ------------------------------------------------------------
    #  Save / load / SVG
    # ------------------------------------------------------------
    def generate_svg(self, bordered: bool = False):
        return generate_svg(self, bordered=bordered)

    def emit_svg(self):
        # Preview mirrors the drawing area, so it always uses borders.
        self.svgCodeChanged.emit(generate_svg(self, bordered=True))

    def load_state(self, state: dict):
        load_state(self, state)

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
        self._update_snap_indicator(scene_pos)
        self.mouse.on_mouse_moved(scene_pos)

    def _update_snap_indicator(self, scene_pos):
        if scene_pos is None or not self.grid_item.snap_enabled:
            self.snap_indicator.hide_indicator()
            return
        if self.transform.is_transforming():
            # Transforms don't snap — showing the dot would be misleading.
            self.snap_indicator.hide_indicator()
            return
        self.snap_indicator.show_at(self.grid_item.snap_to(scene_pos))

    def clear_hover(self):
        self.mouse.clear_hover()

    # ------------------------------------------------------------
    #  NEW: Signal handlers for Document changes
    # ------------------------------------------------------------
    def _on_points_linked(self, junction):
        """Called when points are linked. Update the visual 'linked' flags."""
        self.link_manager.sync_linked_flags()

    def _on_points_unlinked(self, point):
        """Called when a point is unlinked. Update the visual 'linked' flags."""
        self.link_manager.sync_linked_flags()

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        self.mouse.on_point_moved(point)

    def on_curve_changed(self):
        self.request_scene_update(update_svg=True, update_fills=True)

    def mirror_selection(self, axis: str) -> bool:
        return self.selection_ops.mirror_selection(axis)

    def center_selection(self, axis: str) -> bool:
        return self.selection_ops.center_selection(axis)

    def move_selected_points(self, dx: float, dy: float) -> bool:
        return self.selection_ops.move_selected_points(dx, dy)

    def snap_selection_to_grid(self) -> int:
        return self.selection_ops.snap_selection_to_grid()

    def delete_selection(self) -> int:
        return self.selection_ops.delete_selection()

    def hide_points(self) -> bool:
        return self.selection_ops.hide_points()

    def show_all_points(self) -> int:
        return self.selection_ops.show_all_points()

    def set_curve_color(self, color):
        self.curve_color = QColor(color)
        for curve in self.curves:
            curve.set_color(self.curve_color)
        if self.pending_curve is not None:
            self.pending_curve.set_color(self.curve_color)
        self.shape_manager.apply_curve_colors()

    def set_viewbox(self, width: float, height: float):
        """Resize the viewbox (kept centered on origin). The artboard is
        untouched. Called by MainWindow on Canvas Size confirmation, and by
        load_state when restoring a saved document."""
        new_rect = QRectF(-width / 2, -height / 2, width, height)
        if new_rect == self.viewbox:
            return
        self.viewbox = new_rect
        self.viewbox_item.setRect(new_rect)
        self.background.refit()
        self.emit_svg()


    def request_scene_update(self, update_svg: bool = True, update_fills: bool = True):
        """Call this during rapid changes (e.g., mouse drags) to debounce
        heavy operations and prevent event-loop starvation or segfaults."""
        if update_svg:
            self._pending_svg = True
        if update_fills:
            self._pending_fills = True
        self._update_timer.start()

    def _apply_pending_updates(self):
        """Executed 100ms after the last rapid change."""
        if self._pending_svg:
            self._pending_svg = False
            self.emit_svg()
        if self._pending_fills:
            self._pending_fills = False
            self.shape_manager.update_fills()

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        self.clear_hover()
        self.transform.end_transform(commit=False)
        self.set_selected_point(None)
        self.builder.clear()
        self.snap_indicator.hide_indicator()

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
        self.background.remove()
        self.emit_svg()
        self.link_manager.reset()
        self.shape_manager.reset()
        self.messageLogged.emit("Scene cleared")
