# bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor, QPainter
from PySide6.QtCore import QRectF, Qt

from settings import (CURVE_PEN_WIDTH, CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH, HOVER_CURVE_COLOR,
                      HOVER_TOLERANCE, SVG_PRECISION, HIDDEN_CURVE_COLOR, SHAPE_SELECTED_CURVE_COLOR)
from control_point import ControlPoint

GOLDEN_RATIO_CONJUGATE = 0.618033988749895
FIRST_HUE_OFFSET = 0.55

from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from bezier_scene import BezierScene


class BezierCurve(QGraphicsItem):
    _next_id = 1

    def __init__(self, scene):
        super().__init__()
        self.id = BezierCurve._next_id
        BezierCurve._next_id += 1
        self.name = f"Curve {self.id}"

        hue = (FIRST_HUE_OFFSET + (self.id - 1) * GOLDEN_RATIO_CONJUGATE) % 1.0
        self.color = QColor.fromHsvF(hue, 0.75, 0.85)
        self.points: list[ControlPoint] = []
        self.highlighted = False
        self.hovered = False
        self.committed = False
        self.points_hidden = False
        self.shape_selected = False
        self._pen_normal = QPen(self.color, CURVE_PEN_WIDTH)
        self._pen_hover = QPen(HOVER_CURVE_COLOR, CURVE_PEN_WIDTH)
        self._pen_highlight = QPen(CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH)
        self._pen_hidden = QPen(HIDDEN_CURVE_COLOR, CURVE_PEN_WIDTH)
        self._pen_shape_selected = QPen(SHAPE_SELECTED_CURVE_COLOR, CURVE_PEN_WIDTH)

        self._path = QPainterPath()
        self._hit_path = QPainterPath()

        self.setZValue(-1)
        scene.addItem(self)          # add *self*, not a child path item

    @property
    def _scene(self) -> "BezierScene":
        return cast("BezierScene", super().scene())


    # ---------------------------------------------------------------
    #  QGraphicsItem API
    # ---------------------------------------------------------------
    def boundingRect(self):
        if self._hit_path.isEmpty():
            return QRectF()
        pad = max(CURVE_PEN_WIDTH, CURVE_DRAG_PEN_WIDTH) / 2 + 1
        return self._hit_path.boundingRect().adjusted(-pad, -pad, pad, pad)

    def shape(self):
        return self._hit_path

    def paint(self, painter, option, widget=None):
        if self._path.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.highlighted:
            pen = self._pen_highlight
        elif self.shape_selected:
            pen = self._pen_shape_selected
        elif self.hovered:
            pen = self._pen_hover
        elif self.points_hidden:
            pen = self._pen_hidden
        else:
            pen = self._pen_normal
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)


    # ---------------------------------------------------------------
    #  Construction
    # ---------------------------------------------------------------
    def add_point(self, pos):
        pt = ControlPoint(pos, self, len(self.points))
        self._scene.addItem(pt)  # ← sibling, not child
        self.points.append(pt)
        if self.committed:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.rebuild_path()
        return pt

    def is_complete(self):
        return len(self.points) == 4

    # ---------------------------------------------------------------
    #  Geometry
    # ---------------------------------------------------------------
    def positions(self):
        return [p.pos() for p in self.points]

    def rebuild_path(self):
        self.prepareGeometryChange()     # tell the scene bounds are about to change
        pts = self.positions()
        path = QPainterPath()
        if len(pts) == 4:
            path.moveTo(pts[0])
            path.cubicTo(pts[1], pts[2], pts[3])
        elif pts:
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
        self._path = path

        stroker = QPainterPathStroker()
        stroker.setWidth(2 * HOVER_TOLERANCE)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)  # ← endpoint hit region
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)  # ← corner hit region
        self._hit_path = stroker.createStroke(path)

        self.update()

    # ---------------------------------------------------------------
    #  Highlight / hover
    # ---------------------------------------------------------------
    def set_highlighted(self, value):
        if self.highlighted == value:
            return
        self.highlighted = value
        self.update()
        for pt in self.points:
            pt.set_highlighted(value)

    def set_hovered(self, value):
        if self.hovered == value:
            return
        self.hovered = value
        self.update()
        for pt in self.points:
            pt.set_hovered(value)

    def set_shape_selected(self, value):
        if self.shape_selected == value:
            return
        self.shape_selected = value
        self.update()

    def is_near(self, pos):
        if self.points_hidden:
            return False

        if self._hit_path.contains(pos):
            return True

        for pt in self.points:
            p = pt.pos()  # scene coords (points are siblings, curve is at origin)
            dx = p.x() - pos.x()
            dy = p.y() - pos.y()
            if dx * dx + dy * dy <= HOVER_TOLERANCE * HOVER_TOLERANCE:
                return True
        return False

    # ---------------------------------------------------------------
    #  SVG
    # ---------------------------------------------------------------
    def svg_path_string(self):
        if not self.is_complete():
            return ""
        p = SVG_PRECISION
        p0, p1, p2, p3 = self.positions()
        return (f"M {p0.x():.{p}f},{p0.y():.{p}f} "
                f"C {p1.x():.{p}f},{p1.y():.{p}f} "
                f"{p2.x():.{p}f},{p2.y():.{p}f} "
                f"{p3.x():.{p}f},{p3.y():.{p}f}")

    # ---------------------------------------------------------------
    #  Callback from ControlPoint
    # ---------------------------------------------------------------
    def on_point_moved(self):
        self.rebuild_path()
        self._scene.on_curve_changed()

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

    def set_points_hidden(self, value):
        if self.points_hidden == value:
            return
        self.points_hidden = value
        for pt in self.points:
            pt.setVisible(not value)
        self.update()