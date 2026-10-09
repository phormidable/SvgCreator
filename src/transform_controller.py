# transform_controller.py
import math
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

from settings import ROTATION_PIVOT_RADIUS, ROTATION_PIVOT_COLOR


class TransformController:
    """Rotate/scale an active selection around its barycentre."""

    def __init__(self, scene):
        self.scene = scene
        self._mode: str | None = None      # "rotate" | "scale" | None
        self._pivot: QPointF | None = None
        self._ref: float | None = None     # ref angle (rotate) or dist (scale)
        self._starts: dict = {}
        self._last_pos: QPointF | None = None
        self._pivot_item: QGraphicsEllipseItem | None = None

    # ------------------------------------------------------------
    #  State queries
    # ------------------------------------------------------------
    def is_rotating(self) -> bool:
        return self._mode == "rotate"

    def is_scaling(self) -> bool:
        return self._mode == "scale"

    def is_transforming(self) -> bool:
        return self._mode is not None

    # ------------------------------------------------------------
    #  Base points / selection
    # ------------------------------------------------------------
    def _transform_base_points(self):
        """The points whose barycentre is the pivot: the selected shape's, or
        the selected curves'. None if nothing suitable is selected."""
        curves = self._selected_curves()
        if not curves:
            return None
        pts: set = set()
        for c in curves:
            pts.update(c.points)
        return pts

    def _selected_curves(self):
        """Every curve currently part of the selection — shape selection
        (S) and curve selection (A / click) are independent and both count."""
        curves: set = set()
        for shape in self.scene.shape_manager.selected_shapes():
            curves.update(self.scene.ui_curves(shape))
        for c in self.scene.curves:
            if c.curve_selected:
                curves.add(c)
        return list(curves)

    # ------------------------------------------------------------
    #  Start / end
    # ------------------------------------------------------------
    def _start_transform(self, mode: str) -> bool:
        if self.is_transforming():
            return True
        base = self._transform_base_points()
        if not base:
            self.scene.messageLogged.emit(
                "Nothing to transform — select a curve (A or click) or a shape (S) first")
            return False

        cx = sum(p.pos().x() for p in base) / len(base)
        cy = sum(p.pos().y() for p in base) / len(base)

        self._mode = mode
        self._pivot = QPointF(cx, cy)
        self._ref = None  # captured on first move
        self._starts = {
            p: p.pos() for p in self.scene._with_linked(base)}

        self._last_pos = None
        self._show_pivot(cx, cy)
        self.scene.transformModeChanged.emit(True)
        verb = "Rotating" if mode == "rotate" else "Scaling"
        self.scene.messageLogged.emit(
            f"{verb} around ({cx:.1f}, {cy:.1f}) — right-click to validate, Esc to cancel")
        return True

    def _end_transform(self, commit: bool = True):
        if not self.is_transforming():
            return
        mode = self._mode
        if not commit:
            for pt, start in self._starts.items():
                pt.setPos(start)
            self.scene.on_curve_changed()  # one rebuild after restoring
        self._mode = None
        self._pivot = None
        self._ref = None
        self._starts = {}
        self._hide_pivot()
        self.scene.transformModeChanged.emit(False)
        verb = "Rotation" if mode == "rotate" else "Scaling"
        self.scene.messageLogged.emit(
            f"{verb} validated" if commit else f"{verb} cancelled")

    def start_rotation(self) -> bool:
        return self._start_transform("rotate")

    def start_scaling(self) -> bool:
        return self._start_transform("scale")

    def end_transform(self, commit: bool = True):
        self._end_transform(commit)

    # ------------------------------------------------------------
    #  Re-anchor (after an external move, e.g. mirror)
    # ------------------------------------------------------------
    def _reanchor_transform(self):
        """After an external change to positions (e.g. a mirror during an
        active transform), realign the snapshot so the next update continues
        from the current positions instead of the pre-transform ones."""
        if self._pivot is None:
            return
        for p in self._starts:
            self._starts[p] = p.pos()
        last = self._last_pos
        if last is None:
            # No mouse move yet; let the first move capture a fresh reference.
            self._ref = None
            return
        px = self._pivot.x()
        py = self._pivot.y()
        dx, dy = last.x() - px, last.y() - py
        if self.is_rotating():
            self._ref = math.atan2(dy, dx) if (dx or dy) else None
        else:
            dist = math.hypot(dx, dy)
            self._ref = dist if dist > 1e-6 else None

    # ------------------------------------------------------------
    #  Per-move updates
    # ------------------------------------------------------------
    def _update_rotation(self, scene_pos: QPointF):
        if scene_pos is None or self._pivot is None:
            return
        self._last_pos = QPointF(scene_pos)
        px, py = self._pivot.x(), self._pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        if dx == 0.0 and dy == 0.0:
            return
        angle = math.atan2(dy, dx)
        if self._ref is None:
            self._ref = angle
            return
        delta = angle - self._ref
        cos_a, sin_a = math.cos(delta), math.sin(delta)
        for pt, start in self._starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * cos_a - sy * sin_a,
                      py + sx * sin_a + sy * cos_a)

    def _update_scaling(self, scene_pos: QPointF):
        if scene_pos is None or self._pivot is None:
            return
        self._last_pos = QPointF(scene_pos)
        px, py = self._pivot.x(), self._pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return
        if self._ref is None:
            self._ref = dist
            return
        ratio = dist / self._ref
        ratio = max(0.05, min(ratio, 50.0))  # guard against collapse/explosion
        for pt, start in self._starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * ratio, py + sy * ratio)

    # ------------------------------------------------------------
    #  Pivot marker
    # ------------------------------------------------------------
    def _show_pivot(self, x: float, y: float):
        r = ROTATION_PIVOT_RADIUS
        item = QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
        item.setBrush(QBrush(ROTATION_PIVOT_COLOR))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setZValue(1000)
        item.setPos(x, y)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.scene.addItem(item)
        self._pivot_item = item

    def _hide_pivot(self):
        if self._pivot_item is not None:
            self.scene.removeItem(self._pivot_item)
            self._pivot_item = None