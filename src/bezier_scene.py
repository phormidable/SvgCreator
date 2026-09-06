# bezier_scene.py
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPathItem
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainterPath, QPen
from settings import (
    VIEWBOX_RECT,
    CURVE_PEN_COLOR,
    CURVE_PEN_WIDTH,
    SVG_STROKE_COLOR,
    SVG_STROKE_WIDTH,
    SVG_FILL,
)
from control_point import ControlPoint

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()   # emitted when points move or selection changes

    def __init__(self):
        super().__init__()
        self.curve_groups = []          # list of lists of ControlPoint (4 each)
        self.current_points = []        # points being placed for current curve
        self.path_item = QGraphicsPathItem()
        self.addItem(self.path_item)
        self.mode = "create"
        self.selected_curve_idx = -1    # index of the curve shown in the info panel

        self.setSceneRect(VIEWBOX_RECT)

    # ------------------------------------------------------------
    #  Mouse interaction – creation only in "create" mode
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode == "create":
            pos = event.scenePos()
            index = len(self.current_points)
            pt = ControlPoint(pos, self, index)
            self.addItem(pt)
            self.current_points.append(pt)

            if len(self.current_points) == 4:
                self.curve_groups.append(self.current_points)
                self.selected_curve_idx = len(self.curve_groups) - 1
                self.current_points = []
                self.pointsChanged.emit()   # notify that selection changed

            self.rebuild_visual_path()
            self.emit_svg()
            return

        super().mousePressEvent(event)

    # ------------------------------------------------------------
    #  Called when a point is dragged
    # ------------------------------------------------------------
    def on_point_moved(self):
        self.rebuild_visual_path()
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Rebuild the on‑canvas drawing
    # ------------------------------------------------------------
    def rebuild_visual_path(self):
        path = QPainterPath()

        for group in self.curve_groups:
            if len(group) == 4:
                p0, p1, p2, p3 = [p.pos() for p in group]
                path.moveTo(p0)
                path.cubicTo(p1, p2, p3)

        if self.current_points:
            pts = [p.pos() for p in self.current_points]
            if len(pts) == 1:
                path.moveTo(pts[0])
            elif len(pts) == 2:
                path.moveTo(pts[0])
                path.lineTo(pts[1])
            elif len(pts) == 3:
                path.moveTo(pts[0])
                path.lineTo(pts[1])
                path.lineTo(pts[2])

        self.path_item.setPath(path)
        self.path_item.setPen(QPen(CURVE_PEN_COLOR, CURVE_PEN_WIDTH))

    # ------------------------------------------------------------
    #  SVG generation
    # ------------------------------------------------------------
    def generate_svg(self):
        path_commands = []
        for group in self.curve_groups:
            if len(group) == 4:
                p0, p1, p2, p3 = [p.pos() for p in group]
                path_commands.append(
                    f"M {p0.x():.2f},{p0.y():.2f} "
                    f"C {p1.x():.2f},{p1.y():.2f} "
                    f"{p2.x():.2f},{p2.y():.2f} "
                    f"{p3.x():.2f},{p3.y():.2f}"
                )

        if not path_commands:
            return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX_RECT.x()} {VIEWBOX_RECT.y()} {VIEWBOX_RECT.width()} {VIEWBOX_RECT.height()}" width="100%" height="100%"></svg>'

        d_string = " ".join(path_commands)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX_RECT.x()} {VIEWBOX_RECT.y()} {VIEWBOX_RECT.width()} {VIEWBOX_RECT.height()}" width="100%" height="100%">'
            f'<path d="{d_string}" fill="{SVG_FILL}" stroke="{SVG_STROKE_COLOR}" stroke-width="{SVG_STROKE_WIDTH}"/>'
            '</svg>'
        )

    def emit_svg(self):
        self.svgCodeChanged.emit(self.generate_svg())

    # ------------------------------------------------------------
    #  Access / modify points of the selected curve
    # ------------------------------------------------------------
    def get_selected_curve(self):
        if 0 <= self.selected_curve_idx < len(self.curve_groups):
            return self.curve_groups[self.selected_curve_idx]
        return None

    def move_selected_point(self, point_idx, pos):
        curve = self.get_selected_curve()
        if curve and 0 <= point_idx < len(curve):
            curve[point_idx].setPos(pos)
            self.on_point_moved()

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        for group in self.curve_groups:
            for pt in group:
                self.removeItem(pt)
        for pt in self.current_points:
            self.removeItem(pt)
        self.curve_groups.clear()
        self.current_points.clear()
        self.selected_curve_idx = -1
        self.rebuild_visual_path()
        self.emit_svg()
        self.pointsChanged.emit()