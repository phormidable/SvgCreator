# scene/bezier_scene.py
from PySide6.QtCore import Signal
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (QGraphicsScene, QGraphicsRectItem)

from .scene_io import generate_svg, save_state, load_state
from core.settings import ARTBOARD_RECT, VIEWBOX_RECT, VIEWBOX_BACKGROUND_COLOR, VIEWBOX_BORDER_COLOR, VIEWBOX_BORDER_WIDTH, DEFAULT_CURVE_COLOR, GRID_DEFAULT_SPACING
from core.model import Document
from .link_manager import LinkManager
from .items.bezier_curve import BezierCurve
from .items.snap_indicator import SnapIndicator
from .items.grid_item import GridItem
from .shape_manager import ShapeManager
from .selection import Selection
from .transform_controller import TransformController
from .preset_controller import PresetController
from .model_registry import ModelRegistry
from .curve_builder import CurveBuilder
from .curve_renderer import CurveRenderer
from .point_renderer import PointRenderer
from .mouse_controller import MouseController
from .selection_ops import SelectionOps
from .background_image import BackgroundImage
from .items.origin_marker import OriginMarker
from .clipboard import Clipboard
from .undo_manager import UndoManager



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

        # ---- State ----
        self.curves = []              # committed BezierCurve objects
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
    #def start_rotation(self) -> bool:
     #   return self.transform.start_rotation()

    #def start_scaling(self) -> bool:
     #   return self.transform.start_scaling()

    #def start_move(self) -> bool:
     #   return self.transform.start_move()

    def load_background_image(self, filepath):
        return self.background.load(filepath)

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

    #def set_degree(self, degree: int):
     #   self.builder.set_degree(degree)

    #def discard_current_points(self):
     #   self.builder.discard()

    #def cancel_pending_curve(self) -> bool:
     #   return self.builder.cancel_pending_curve()

    #def set_grid_visible(self, visible: bool):
     #   self.grid_item.setVisible(visible)

    #def set_grid_spacing(self, spacing: int):
     #   self.grid_item.set_spacing(spacing)

    def set_snap_enabled(self, enabled: bool):
        self.grid_item.set_snap_enabled(enabled)
        if not enabled:
            self.snap_indicator.hide_indicator()

    #def handle_transform_key(self, event) -> bool:
     #   return self.transform.handle_key(event)

    def set_selected_point(self, point):
        self.selection.set_point(point)

    #def toggle_selection(self, point):
     #   self.selection.toggle_point(point)

    def clear_selection(self):
        self.selection.clear()

    def select_curve_under_hover(self, add: bool = False) -> bool:
        return self.selection_ops.select_curve_under_hover(add=add)

    #def select_in_rect(self, rect, add: bool = False) -> int:
     #   return self.selection.select_in_rect(rect, add=add)

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

    def on_point_moved(self, point):
        """Called by ControlPoint when its position changed."""
        self.mouse.on_point_moved(point)

    def on_curve_changed(self):
        self.emit_svg()
        self.shape_manager.update_fills()

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
