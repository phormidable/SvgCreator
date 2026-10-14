# transform_controller.py
import math
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem

from core.settings import ROTATION_PIVOT_RADIUS, ROTATION_PIVOT_COLOR


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
        self._typed_angle: str | None = None

    # ------------------------------------------------------------
    #  State queries
    # ------------------------------------------------------------
    def is_rotating(self) -> bool:
        return self._mode == "rotate"

    def is_moving(self) -> bool:
        return self._mode == "move"

    def is_scaling(self) -> bool:
        return self._mode == "scale"

    def is_transforming(self) -> bool:
        return self._mode is not None

    # ------------------------------------------------------------
    #  For typing a rotation
    # ------------------------------------------------------------
    def handle_key(self, event) -> bool:
        """Digit/decimal/minus/backspace/enter input while rotating. Consumes
        the event and returns True on a hit; False means 'not mine'."""
        if not self.is_rotating():
            return False

        K = Qt.Key
        key = event.key()

        if key in (K.Key_Return, K.Key_Enter):
            self.scene.end_transform(commit=True)
            return True

        if key == K.Key_Backspace:
            if self._typed_angle:
                self._typed_angle = self._typed_angle[:-1] or None
                self._typed_angle_changed()
            return True

        text = event.text()
        if text in ("-", ".") or (len(text) == 1 and text.isdigit()):
            if text == "-" and self._typed_angle:
                return True  # minus only at the start
            if text == "." and self._typed_angle and "." in self._typed_angle:
                return True  # one dot, max
            self._typed_angle = (self._typed_angle or "") + text
            self._typed_angle_changed()
            return True

        return False

    def _typed_angle_changed(self):
        self._apply_typed_rotation()
        self.scene.transformTypedChanged.emit(self._typed_angle or "")

    def _apply_typed_rotation(self):
        """Rotate the selection to match the typed buffer, from the original
        start positions. Idempotent: successive calls overwrite, they don't
        accumulate — `_apply_rotation` always reads from `_starts`."""
        if self._pivot is None:
            return
        if not self._typed_angle:
            angle = 0.0  # buffer emptied → undo any typed rotation
        else:
            try:
                angle = float(self._typed_angle)
            except ValueError:
                return  # "-", ".", "90." — keep the current state
        self._apply_rotation(math.radians(angle))

    def cancel_typed_input(self) -> bool:
        """Clear the typed buffer only. Returns True if there was one."""
        if self._typed_angle is None:
            return False
        self._typed_angle = None
        self._typed_angle_changed()
        return True

    # ------------------------------------------------------------
    #  Base points / selection
    # ------------------------------------------------------------
    def _transform_base_points(self):
        """Every point the user has selected. Selection.points already
        aggregates points, curves, chains and shapes, so we read it directly."""
        pts = set(self.scene.selection.points)
        return pts or None

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

        cx = sum(p.model_pos().x() for p in base) / len(base)
        cy = sum(p.model_pos().y() for p in base) / len(base)

        self._mode = mode
        self._pivot = QPointF(cx, cy)
        self._ref = None
        self._typed_angle = None
        self._starts = {p: p.model_pos() for p in self.scene._with_linked(base)}
        self._last_pos = None

        if mode != "move":
            self._show_pivot(cx, cy)
        self.scene.transformModeChanged.emit(True)

        if mode == "move":
            self.scene.messageLogged.emit("Moving selection — left-click to validate, Esc to cancel")
        else:
            verb = "Rotating" if mode == "rotate" else "Scaling"
            self.scene.messageLogged.emit(
                f"{verb} around ({cx:.1f}, {cy:.1f}) — left-click to validate, Esc to cancel")
        return True

    def _end_transform(self, commit: bool = True):
        if not self.is_transforming():
            return
        mode = self._mode

        if not commit:
            for pt, start in self._starts.items():
                pt.setPos(start)
            self.scene.on_curve_changed()

        self._mode = None
        self._pivot = None
        self._ref = None
        self._starts = {}
        self._typed_angle = None
        self._hide_pivot()
        self.scene.transformModeChanged.emit(False)
        verb = {"rotate": "Rotation", "scale": "Scaling", "move": "Move"}[mode]
        self.scene.messageLogged.emit(f"{verb} validated" if commit else f"{verb} cancelled")
        self.scene.transformTypedChanged.emit("")

    def start_rotation(self) -> bool:
        return self._start_transform("rotate")

    def start_scaling(self) -> bool:
        return self._start_transform("scale")

    def start_move(self) -> bool:
        return self._start_transform("move")

    def end_transform(self, commit: bool = True):
        self._end_transform(commit)

    # ------------------------------------------------------------
    #  Re-anchor (after an external move, e.g. mirror)
    # ------------------------------------------------------------
    def _reanchor_transform(self):
        if self._pivot is None:
            return
        for p in self._starts:
            self._starts[p] = p.pos()
        last = self._last_pos
        if last is None:
            self._ref = None
            return
        if self.is_moving():
            self._ref = QPointF(last)
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
        if self._typed_angle is not None:
            return  # user is typing; the cursor no longer drives the angle
        self._last_pos = QPointF(scene_pos)
        px, py = self._pivot.x(), self._pivot.y()
        dx, dy = scene_pos.x() - px, scene_pos.y() - py
        if dx == 0.0 and dy == 0.0:
            return
        angle = math.atan2(dy, dx)
        if self._ref is None:
            self._ref = angle
            return
        self._apply_rotation(angle - self._ref)

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

    def _update_move(self, scene_pos: QPointF):
        if scene_pos is None:
            return
        self._last_pos = QPointF(scene_pos)
        if self._ref is None:
            self._ref = QPointF(scene_pos)
            return
        dx = scene_pos.x() - self._ref.x()
        dy = scene_pos.y() - self._ref.y()
        for pt, start in self._starts.items():
            pt.setPos(start.x() + dx, start.y() + dy)

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

    def _apply_rotation(self, delta: float):
        px, py = self._pivot.x(), self._pivot.y()
        cos_a, sin_a = math.cos(delta), math.sin(delta)
        for pt, start in self._starts.items():
            sx, sy = start.x() - px, start.y() - py
            pt.setPos(px + sx * cos_a - sy * sin_a,
                      py + sx * sin_a + sy * cos_a)