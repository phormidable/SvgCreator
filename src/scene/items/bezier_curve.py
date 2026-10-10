# scene/items/bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QColor, QPainter
from PySide6.QtCore import QRectF, Qt

from core.settings import (
    CURVE_PEN_WIDTH, SHAPE_SELECTED_CURVE_PEN_WIDTH,
    CURVE_SELECTED_PEN_WIDTH, HOVER_TOLERANCE,
)

from scene.items.control_point import ControlPoint

from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from scene.bezier_scene import BezierScene


class BezierCurve(QGraphicsItem):
    _next_id = 1

    def __init__(self, scene, degree: int = 3):
        super().__init__()
        self.id = BezierCurve._next_id
        BezierCurve._next_id += 1
        self.name = f"Curve {self.id}"
        self.degree = degree
        self.color = QColor(scene.curve_color)
        self.points: list[ControlPoint] = []

        self.committed = False
        self.points_hidden = False

        self._path = QPainterPath()
        self._hit_path = QPainterPath()

        self.setZValue(-1)
        scene.addItem(self)

    @property
    def _scene(self) -> "BezierScene":
        return cast("BezierScene", super().scene())

    # ---------------------------------------------------------------
    #  Derived interaction state (reads through Selection)
    # ---------------------------------------------------------------
    @property
    def hovered(self):
        scene = self.scene()
        if scene is None:
            return False
        return scene.selection.hovered_curve is self

    @property
    def focused(self):
        scene = self.scene()
        if scene is None:
            return False
        return (scene.selection.hovered_curve is self
                and scene.selection.focused_point is None)

    @property
    def shape_selected(self):
        scene = self.scene()
        if scene is None:
            return False
        return scene.selection.is_curve_shape_selected(self)

    @property
    def curve_selected(self):
        scene = self.scene()
        if scene is None:
            return False
        return scene.selection.is_curve_selected(self)

    # ---------------------------------------------------------------
    #  QGraphicsItem API
    # ---------------------------------------------------------------
    def boundingRect(self):
        if self._hit_path.isEmpty():
            return QRectF()
        pad = max(CURVE_PEN_WIDTH, SHAPE_SELECTED_CURVE_PEN_WIDTH, CURVE_SELECTED_PEN_WIDTH) / 2 + 1
        return self._hit_path.boundingRect().adjusted(-pad, -pad, pad, pad)

    def is_complete(self):
        return len(self.points) == self.degree + 1

    def shape(self):
        return self._hit_path

    def paint(self, painter, option, widget=None):
        if self._path.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(self._scene.curve_renderer.pen_for(self))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

    # ---------------------------------------------------------------
    #  Construction
    # ---------------------------------------------------------------
    def add_point(self, pos):
        pt = ControlPoint(pos, self, len(self.points))
        self._scene.addItem(pt)
        self.points.append(pt)
        if self.committed:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.rebuild_path()
        return pt

    # ---------------------------------------------------------------
    #  Geometry
    # ---------------------------------------------------------------
    def positions(self):
        return [p.pos() for p in self.points]

    def rebuild_path(self):
        self.prepareGeometryChange()
        self._path, self._hit_path = self._scene.curve_renderer.paths_for(
            self.positions(), self.degree)
        self.update()

    def set_color(self, color):
        self.color = QColor(color)
        self.update()

    def is_near(self, pos):
        if self.points_hidden:
            return False
        if self._hit_path.contains(pos):
            return True
        for pt in self.points:
            p = pt.pos()
            dx = p.x() - pos.x()
            dy = p.y() - pos.y()
            if dx * dx + dy * dy <= HOVER_TOLERANCE * HOVER_TOLERANCE:
                return True
        return False

    def cubic_segment(self, start_pt):
        """Return (c1_pos, c2_pos, end_pt) describing a cubic that traces
        the same path as this curve, starting from `start_pt` (which must
        be one of the two endpoints). `end_pt` is the point at the other end.
        Quadratics are converted to their exact cubic equivalent."""
        pts = self.points
        if start_pt is pts[0]:
            ctrl = pts[1:-1]
            end = pts[-1]
        else:
            ctrl = list(reversed(pts[1:-1]))
            end = pts[0]
        if self.degree == 3:
            return ctrl[0].pos(), ctrl[1].pos(), end
        p0 = start_pt.pos()
        p1 = ctrl[0].pos()
        p2 = end.pos()
        c1 = p0 + (p1 - p0) * (2.0 / 3.0)
        c2 = p2 + (p1 - p2) * (2.0 / 3.0)
        return c1, c2, end

    # ---------------------------------------------------------------
    #  Callback from ControlPoint
    # ---------------------------------------------------------------
    def on_point_moved(self):
        self.rebuild_path()
        self._scene.on_curve_changed()

    # ---------------------------------------------------------------
    #  Hidden points
    # ---------------------------------------------------------------
    def set_points_hidden(self, value):
        if self.points_hidden == value:
            return
        self.points_hidden = value
        for pt in self.points:
            pt.setVisible(not value)
        self.update()

    # ---------------------------------------------------------------
    #  Teardown
    # ---------------------------------------------------------------
    def dispose(self):
        assert self not in self._scene.curves
        for pt in self.points:
            self._scene.link_manager.unlink_point(pt)
            self._scene.removeItem(pt)
        self.points.clear()
        self._scene.removeItem(self)