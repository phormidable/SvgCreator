# bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor, QPainter
from PySide6.QtCore import QRectF, Qt

from settings import (CURVE_PEN_WIDTH, HOVER_COLOR_FOCUS, CURVE_SELECTED_PEN_COLOR, CURVE_SELECTED_PEN_WIDTH, HOVER_COLOR,
                      HOVER_TOLERANCE, SVG_PRECISION, HIDDEN_CURVE_COLOR, SHAPE_SELECTED_CURVE_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH)

from control_point import ControlPoint

from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from bezier_scene import BezierScene


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
        self.shape_selected = False
        #self.curve_selected = False

        self._pen_normal = QPen(self.color, CURVE_PEN_WIDTH)
        self._pen_hover = QPen(HOVER_COLOR, CURVE_PEN_WIDTH)
        self._pen_hidden = QPen(HIDDEN_CURVE_COLOR, CURVE_PEN_WIDTH)
        self._pen_shape_selected = QPen(SHAPE_SELECTED_CURVE_COLOR, SHAPE_SELECTED_CURVE_PEN_WIDTH)
        self._pen_curve_selected = QPen(CURVE_SELECTED_PEN_COLOR, CURVE_SELECTED_PEN_WIDTH)
        self._pen_focus = QPen(HOVER_COLOR_FOCUS, CURVE_PEN_WIDTH)
        self._path = QPainterPath()
        self._hit_path = QPainterPath()

        self.setZValue(-1)
        scene.addItem(self)          # add *self*, not a child path item

    @property
    def _scene(self) -> "BezierScene":
        return cast("BezierScene", super().scene())

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
        #if self.highlighted:
         #   pen = self._pen_highlight
        if self.hovered:
            pen = self._pen_hover
        elif self.shape_selected:
            pen = self._pen_shape_selected
        elif self.curve_selected:
            pen = self._pen_curve_selected
        elif self.focused:
            pen = self._pen_focus

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

    # ---------------------------------------------------------------
    #  Geometry
    # ---------------------------------------------------------------
    def positions(self):
        return [p.pos() for p in self.points]

    def rebuild_path(self):
        self.prepareGeometryChange()     # tell the scene bounds are about to change
        pts = self.positions()
        path = QPainterPath()
        if len(pts) == self.degree + 1:
            path.moveTo(pts[0])
            if self.degree == 2:
                path.quadTo(pts[1], pts[2])
            else:
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

    def set_color(self, color):
        self.color = QColor(color)
        self._pen_normal = QPen(self.color, CURVE_PEN_WIDTH)
        self.update()

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
        pts = self.positions()
        if len(pts) != self.degree + 1:
            return ""

        p = SVG_PRECISION
        if self.degree == 2:
            p0, p1, p2 = pts
            return (f"M {p0.x():.{p}f},{p0.y():.{p}f} "
                    f"Q {p1.x():.{p}f},{p1.y():.{p}f} "
                    f"{p2.x():.{p}f},{p2.y():.{p}f}")
        p0, p1, p2, p3 = pts
        return (f"M {p0.x():.{p}f},{p0.y():.{p}f} "
                f"C {p1.x():.{p}f},{p1.y():.{p}f} "
                f"{p2.x():.{p}f},{p2.y():.{p}f} "
                f"{p3.x():.{p}f},{p3.y():.{p}f}")

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