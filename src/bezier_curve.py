# bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QPainterPathStroker, QPen, QColor, QPainter
from PySide6.QtCore import QRectF, Qt

from settings import (CURVE_PEN_WIDTH, CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH,
                      HOVER_CURVE_COLOR, HOVER_TOLERANCE)
from control_point import ControlPoint

GOLDEN_RATIO_CONJUGATE = 0.618033988749895
FIRST_HUE_OFFSET = 0.55


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

        self._path = QPainterPath()
        self._hit_path = QPainterPath()

        self.setZValue(-1)
        scene.addItem(self)          # add *self*, not a child path item

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
            pen = QPen(CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH)
        elif self.hovered:
            pen = QPen(HOVER_CURVE_COLOR, CURVE_PEN_WIDTH)
        else:
            pen = QPen(self.color, CURVE_PEN_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

    # ---------------------------------------------------------------
    #  Construction
    # ---------------------------------------------------------------
    def add_point(self, pos):
        pt = ControlPoint(pos, self, len(self.points))
        self.scene().addItem(pt)  # ← sibling, not child
        self.points.append(pt)
        if self.committed:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.rebuild_path()
        self.scene().on_curve_changed()
        return pt

    def is_complete(self):
        return len(self.points) == 4

    # ---------------------------------------------------------------
    #  Geometry
    # ---------------------------------------------------------------
    def positions(self):
        return [p.pos() for p in self.points]

    def move_point(self, point_idx, pos):
        if 0 <= point_idx < len(self.points):
            self.points[point_idx].setPos(pos)

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

    def is_near(self, pos, tolerance):
        # pos is scene coords; _hit_path is also in scene coords (curve is at origin)
        if self._hit_path.contains(pos):
            return True
        r2 = tolerance * tolerance
        for pt in self.points:
            p = pt.pos()  # scene coords (sibling point)
            dx = p.x() - pos.x()
            dy = p.y() - pos.y()
            if dx * dx + dy * dy <= r2:
                return True
        return False

    # ---------------------------------------------------------------
    #  SVG
    # ---------------------------------------------------------------
    def svg_path_string(self):
        if not self.is_complete():
            return ""
        p0, p1, p2, p3 = self.positions()
        return (f"M {p0.x():.2f},{p0.y():.2f} "
                f"C {p1.x():.2f},{p1.y():.2f} "
                f"{p2.x():.2f},{p2.y():.2f} "
                f"{p3.x():.2f},{p3.y():.2f}")

    # ---------------------------------------------------------------
    #  Callback from ControlPoint
    # ---------------------------------------------------------------
    def on_point_moved(self):
        self.rebuild_path()
        self.scene().on_curve_changed()

    # ---------------------------------------------------------------
    #  Teardown
    # ---------------------------------------------------------------
    def dispose(self):
        for pt in self.points:
            self.scene().removeItem(pt)
        self.points.clear()
        self.scene().removeItem(self)