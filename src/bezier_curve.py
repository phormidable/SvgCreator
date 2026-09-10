# bezier_curve.py
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PySide6.QtGui import QPainterPath, QPen
from settings import CURVE_PEN_COLOR, CURVE_PEN_WIDTH, CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH
from control_point import ControlPoint


class BezierCurve:
    _next_id = 1

    def __init__(self, scene):
        self.scene = scene
        self.id = BezierCurve._next_id
        BezierCurve._next_id += 1
        self.name = f"Curve {self.id}"

        self.points: list[ControlPoint] = []
        self.path_item = QGraphicsPathItem()
        self.path_item.setZValue(-1)
        scene.addItem(self.path_item)

        self.highlighted = False
        self.committed = False   # True once it belongs to scene.curves

    # ---- construction ----
    def add_point(self, pos):
        pt = ControlPoint(pos, self, len(self.points))
        self.scene.addItem(pt)
        self.points.append(pt)
        if self.committed:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.rebuild_path()
        self.scene.on_curve_changed()
        return pt

    def is_complete(self):
        return len(self.points) == 4

    # ---- geometry ----
    def positions(self):
        return [p.pos() for p in self.points]

    def move_point(self, point_idx, pos):
        self.points[point_idx].setPos(pos)

    def rebuild_path(self):
        path = QPainterPath()
        pts = self.positions()
        if pts:
            path.moveTo(pts[0])
            for p in pts[1:]:
                path.lineTo(p)
            if len(pts) == 4:
                path = QPainterPath()
                path.moveTo(pts[0])
                path.cubicTo(pts[1], pts[2], pts[3])
        self.path_item.setPath(path)
        if self.highlighted:
            self.path_item.setPen(QPen(CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH))
        else:
            self.path_item.setPen(QPen(CURVE_PEN_COLOR, CURVE_PEN_WIDTH))

    # ---- highlight ----
    def set_highlighted(self, value):
        if self.highlighted == value:
            return
        self.highlighted = value
        for pt in self.points:
            pt.set_highlighted(value)
        self.rebuild_path()

    # ---- SVG ----
    def svg_path_string(self):
        if not self.is_complete():
            return ""
        p0, p1, p2, p3 = self.positions()
        return (f"M {p0.x():.2f},{p0.y():.2f} "
                f"C {p1.x():.2f},{p1.y():.2f} "
                f"{p2.x():.2f},{p2.y():.2f} "
                f"{p3.x():.2f},{p3.y():.2f}")

    # ---- callback from ControlPoint ----
    def on_point_moved(self):
        self.rebuild_path()
        self.scene.on_curve_changed()

    # ---- teardown ----
    def dispose(self):
        for pt in self.points:
            self.scene.removeItem(pt)
        self.scene.removeItem(self.path_item)