# scene/mouse_controller.py
"""MouseController: all pointer interaction for the drawing area.

Owns:
- create-mode click → CurveBuilder
- preset placement click
- point press → selection collapse / drag start
- rubber-band selection rectangle
- drag propagation to sibling / multi-selected points
- hover tracking (hovered curve + focused point)

The scene keeps one-line ``mousePressEvent`` / ``mouseMoveEvent`` /
``mouseReleaseEvent`` wrappers, plus ``on_mouse_moved`` (forwarded from
the view's ``mouseMoved`` signal) and ``clear_hover`` as thin delegates.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsRectItem

from core.settings import HOVER_TOLERANCE
from .items.control_point import ControlPoint


class MouseController:
    def __init__(self, scene):
        self.scene = scene

        # ---- Drag state ----
        self.dragging_point: ControlPoint | None = None
        self._pending_collapse_point: ControlPoint | None = None
        self._drag_press_pos: QPointF | None = None
        self._drag_targets: dict[ControlPoint, QPointF] = {}
        self._drag_primary_start: QPointF | None = None
        self._ensuring_visible = False

        # ---- Rubber-band selection rectangle ----
        self._rubber_start: QPointF | None = None
        self._rubber_item = QGraphicsRectItem()
        self._rubber_item.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.DashLine))
        self._rubber_item.setBrush(QColor(0, 120, 215, 40))
        self._rubber_item.setZValue(2000)
        self._rubber_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._rubber_item.setVisible(False)
        scene.addItem(self._rubber_item)

    # ------------------------------------------------------------
    #  Press
    # ------------------------------------------------------------
    def mouse_press(self, event) -> bool:
        """Handle the press. Return True if the caller should forward the
        event to ``super().mousePressEvent`` (needed so Qt's own item-drag
        machinery picks up the ControlPoint we just decided to drag)."""
        if event.button() != Qt.MouseButton.LeftButton:
            return True  # let the base class see right-clicks etc.

        scene = self.scene

        # A pending preset consumes this click, whatever the mode.
        if scene.presets._pending is not None:
            keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            scene.presets.place_preset(event.scenePos(), keep_armed=keep)
            return False

        # ---- Create mode ----
        if scene.mode == "create":
            scene.builder.handle_click(event.scenePos())
            return False

        # ---- Edit mode ----
        views = scene.views()
        if not views:
            return True
        item = scene.itemAt(event.scenePos(), views[0].transform())

        if isinstance(item, ControlPoint) and item.curve.committed:
            self._press_on_point(item, event)
            return True  # forward — Qt drives the item move; we watch.

        # Not on a point. Refresh hover for this exact scene position.
        self._update_hover(event.scenePos())
        if scene.hovered_curve is not None:
            add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            scene.select_curve_under_hover(add=add)
            return False

        # Empty space → begin a rubber-band selection. A click without a
        # drag still clears the selection (done here, on press).
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            scene.clear_selection()
        self._rubber_start = event.scenePos()
        self._rubber_item.setRect(QRectF(self._rubber_start, self._rubber_start))
        self._rubber_item.setVisible(True)
        return False

    def _press_on_point(self, item: ControlPoint, event):
        scene = self.scene
        if item not in scene.selected_points:
            # Several points coincide at a junction, and itemAt returns the
            # topmost. If another curve's endpoint is stacked above the one
            # we selected, the click would land on it and collapse the
            # selection. Prefer a linked sibling that is already selected.
            group = scene.link_manager.group_of(item) or ()
            item = next((pt for pt in group if pt in scene.selected_points), item)

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            scene.toggle_selection(item)
            self.clear_hover()
            return

        # Non-shift: selection collapses to exactly this point — unless the
        # point is already part of a multi-point selection, in which case
        # we defer the collapse to release: a click collapses, a drag keeps
        # the whole selection and moves everything together.
        if item in scene.selected_points and len(scene.selected_points) > 1:
            self._pending_collapse_point = item
        else:
            scene.set_selected_point(item)
            self._pending_collapse_point = None

        self._drag_press_pos = event.scenePos()
        self.clear_hover()
        self.dragging_point = item
        self._start_drag(item)

    # ------------------------------------------------------------
    #  Move
    # ------------------------------------------------------------
    def mouse_move(self, event) -> bool:
        """Return True if the caller should forward to super() before
        calling ``post_mouse_move`` (Qt needs to move the dragged item
        first). Return False to consume the move (rubber-band update)."""
        if self._rubber_start is not None:
            rect = QRectF(self._rubber_start, event.scenePos()).normalized()
            self._rubber_item.setRect(rect)
            return False
        return True

    def post_mouse_move(self, event):
        """Runs after ``super().mouseMoveEvent``, i.e. after Qt has updated
        the primary point's position from the mouse delta. Now we can
        propagate the resulting delta to siblings and multi-selected
        points, and keep the primary in the viewport."""
        if self._pending_collapse_point is not None and self._drag_press_pos is not None:
            press = self._drag_press_pos
            cur = event.scenePos()
            dx, dy = cur.x() - press.x(), cur.y() - press.y()
            if dx * dx + dy * dy > 25:  # ~5 px — real movement, not jitter
                self._pending_collapse_point = None

        if self.dragging_point is not None:
            self._drag_points()

        if self.dragging_point is None or self._ensuring_visible:
            return
        self._ensuring_visible = True
        try:
            pos = event.scenePos()
            target = QRectF(pos.x() - 1, pos.y() - 1, 2, 2)
            for view in self.scene.views():
                view.ensureVisible(target, 60, 60)
        finally:
            self._ensuring_visible = False

    def _drag_points(self):
        scene = self.scene
        # Snap only the primary. Siblings linked to it follow via
        # propagate_move; other selected points are translated rigidly by
        # the resulting delta so a multi-point selection never gets
        # distorted by per-point rounding.
        if scene.grid_item.snap_enabled:
            self.dragging_point.setPos(
                scene.grid_item.snap(self.dragging_point.model_pos()))
        delta = self.dragging_point.model_pos() - self._drag_primary_start
        for pt, start in self._drag_targets.items():
            pt.setPos(start + delta)
        scene.link_manager.update_proximity(self.dragging_point)

    # ------------------------------------------------------------
    #  Release
    # ------------------------------------------------------------
    def mouse_release(self, event) -> bool:
        """Return True if the caller should forward to super() (Qt needs
        to finish the item-drag it started on press)."""
        if event.button() != Qt.MouseButton.LeftButton:
            return True

        scene = self.scene

        if self._rubber_start is not None:
            start = self._rubber_start
            self._rubber_start = None
            self._rubber_item.setVisible(False)
            rect = QRectF(start, event.scenePos()).normalized()
            # A tiny rect means the user just clicked empty space; the
            # selection was already cleared on press.
            if rect.width() >= 3 or rect.height() >= 3:
                add = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                scene.select_in_rect(rect, add=add)
            self._update_hover(event.scenePos())
            return False

        if self.dragging_point is not None:
            pending = self._pending_collapse_point
            self._pending_collapse_point = None
            self._drag_press_pos = None
            self.dragging_point = None
            self._drag_targets = {}
            self._drag_primary_start = None
            scene.link_manager.clear_proximity()

            if pending is not None:
                scene.set_selected_point(pending)

            self._update_hover(event.scenePos())
        return True

    # ------------------------------------------------------------
    #  Hover (driven by the view's mouseMoved signal, not by events)
    # ------------------------------------------------------------
    def on_mouse_moved(self, scene_pos):
        scene = self.scene
        if scene.transform.is_transforming():
            if scene.transform.is_rotating():
                scene.transform._update_rotation(scene_pos)
            elif scene.transform.is_scaling():
                scene.transform._update_scaling(scene_pos)
            else:
                scene.transform._update_move(scene_pos)
            return
        if self.dragging_point is not None:
            return
        if self._rubber_start is not None:
            return
        if scene.mode == "create":
            return
        self._update_hover(scene_pos)

    def clear_hover(self):
        self._set_hover(None, None)

    def _update_hover(self, pos):
        new_hovered = None
        new_focused_pt = None
        if pos is not None:
            tol2 = HOVER_TOLERANCE * HOVER_TOLERANCE
            for curve in reversed(self.scene.curves):
                if not curve.is_near(pos):
                    continue
                new_hovered = curve
                for pt in curve.points:
                    p = pt.model_pos()
                    dx, dy = p.x() - pos.x(), p.y() - pos.y()
                    if dx * dx + dy * dy <= tol2:
                        new_focused_pt = pt
                        break
                break
        self._set_hover(new_hovered, new_focused_pt)

    def _set_hover(self, curve, point):
        scene = self.scene
        old = scene.selection.focused_point
        scene.selection.set_hover(curve, point)
        if old is not point:
            scene.hoveredPointChanged.emit(point)

    # ------------------------------------------------------------
    #  Drag helpers
    # ------------------------------------------------------------
    def _start_drag(self, primary):
        scene = self.scene
        primary_group = scene.link_manager.with_linked({primary})
        seeds = set(scene.selected_points) | {primary}
        self._drag_targets = {
            pt: pt.model_pos()
            for pt in scene.link_manager.with_linked(seeds) - primary_group
        }
        self._drag_primary_start = primary.pos()

    # ------------------------------------------------------------
    #  Point-move callback (invoked by ControlPoint.itemChange)
    # ------------------------------------------------------------
    def on_point_moved(self, point):
        if self.dragging_point is point:
            self.scene.link_manager.update_proximity(point)