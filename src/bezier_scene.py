# bezier_scene.py
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPathItem
from PySide6.QtCore import Signal, Qt, QRectF
from PySide6.QtGui import QPainterPath, QPen
from settings import (
    VIEWBOX_RECT,
    SCENE_MARGIN,
    CURVE_PEN_COLOR,
    CURVE_PEN_WIDTH,
    CURVE_DRAG_PEN_COLOR,
    CURVE_DRAG_PEN_WIDTH,
    SVG_STROKE_COLOR,
    SVG_STROKE_WIDTH,
    SVG_FILL,
)
from control_point import ControlPoint


class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()          # emitted when points move
    curveListChanged = Signal()       # emitted when curves are added/removed
    curveHighlighted = Signal(int)    # emitted when a curve is dragged (for possible UI updates)

    def __init__(self):
        super().__init__()
        # Each curve: tuple (points: list of ControlPoint, path_item: QGraphicsPathItem)
        self.curves = []              # list of (points, path_item)
        self.current_points = []      # points being placed for current curve
        self.mode = "create"
        self.selected_curve_idx = -1  # for the info panel

        # Path item for the current WIP curve (polyline)
        self.wip_path_item = QGraphicsPathItem()
        self.addItem(self.wip_path_item)

        self.setSceneRect(VIEWBOX_RECT)

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if we clicked on a point
            item = self.itemAt(event.scenePos(), self.views()[0].transform())
            if isinstance(item, ControlPoint):
                # Store which curve is being dragged
                self.dragging_curve_idx = item.curve_idx
                self.highlight_curve(self.dragging_curve_idx)
                # Let the item handle the drag
                super().mousePressEvent(event)
                return

            # If in create mode and not on a point, add a point
            if self.mode == "create":
                pos = event.scenePos()
                curve_idx = len(self.curves)  # new curve index
                point_idx = len(self.current_points)
                pt = ControlPoint(pos, self, curve_idx, point_idx)
                self.addItem(pt)
                self.current_points.append(pt)

                if len(self.current_points) == 4:
                    self.finalize_curve()
                else:
                    self.rebuild_wip_path()
                    self.emit_svg()

                # After adding point, we don't call super because we don't want to forward
                return

            # In edit mode and clicked on empty space -> let the view handle panning
            # We will not process here; the view's event handler will manage panning.
            # We just call super to let the event propagate (but the view will decide).
            super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # If we were dragging a curve, un-highlight it
            if hasattr(self, 'dragging_curve_idx'):
                self.unhighlight_curve(self.dragging_curve_idx)
                delattr(self, 'dragging_curve_idx')
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Curve finalization
    # ------------------------------------------------------------
    def finalize_curve(self):
        # Create a path item for this curve
        path_item = QGraphicsPathItem()
        self.addItem(path_item)
        # Store the curve data
        self.curves.append((self.current_points, path_item))
        self.selected_curve_idx = len(self.curves) - 1
        # Reset current points
        self.current_points = []
        # Update the curve's path
        self.rebuild_curve_path(len(self.curves) - 1)
        # Update scene rect
        self.update_scene_rect()
        # Emit signals
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()

    # ------------------------------------------------------------
    #  Rebuild paths
    # ------------------------------------------------------------
    def rebuild_curve_path(self, curve_idx):
        points, path_item = self.curves[curve_idx]
        path = QPainterPath()
        if len(points) == 4:
            p0, p1, p2, p3 = [p.pos() for p in points]
            path.moveTo(p0)
            path.cubicTo(p1, p2, p3)
        path_item.setPath(path)
        # Normal pen (will be overridden by highlight)
        path_item.setPen(QPen(CURVE_PEN_COLOR, CURVE_PEN_WIDTH))

    def rebuild_wip_path(self):
        path = QPainterPath()
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
        self.wip_path_item.setPath(path)
        self.wip_path_item.setPen(QPen(CURVE_PEN_COLOR, CURVE_PEN_WIDTH))

    def rebuild_all_curves(self):
        for i in range(len(self.curves)):
            self.rebuild_curve_path(i)

    # ------------------------------------------------------------
    #  Point moved callback
    # ------------------------------------------------------------
    def on_point_moved(self, curve_idx):
        self.rebuild_curve_path(curve_idx)
        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Highlight / unhighlight curve (for drag feedback)
    # ------------------------------------------------------------
    def highlight_curve(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            _, path_item = self.curves[curve_idx]
            path_item.setPen(QPen(CURVE_DRAG_PEN_COLOR, CURVE_DRAG_PEN_WIDTH))

    def unhighlight_curve(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            _, path_item = self.curves[curve_idx]
            path_item.setPen(QPen(CURVE_PEN_COLOR, CURVE_PEN_WIDTH))

    # ------------------------------------------------------------
    #  Dynamic scene rect
    # ------------------------------------------------------------
    def update_scene_rect(self):
        # Collect all point positions
        all_positions = []
        for points, _ in self.curves:
            all_positions.extend(p.pos() for p in points)
        for p in self.current_points:
            all_positions.append(p.pos())

        if not all_positions:
            # Use default
            self.setSceneRect(VIEWBOX_RECT)
            return

        xs = [p.x() for p in all_positions]
        ys = [p.y() for p in all_positions]
        min_x = min(xs) - SCENE_MARGIN
        max_x = max(xs) + SCENE_MARGIN
        min_y = min(ys) - SCENE_MARGIN
        max_y = max(ys) + SCENE_MARGIN
        rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        self.setSceneRect(rect)

    # ------------------------------------------------------------
    #  SVG generation (uses dynamic rect)
    # ------------------------------------------------------------
    def generate_svg(self):
        path_commands = []
        for points, _ in self.curves:
            if len(points) == 4:
                p0, p1, p2, p3 = [p.pos() for p in points]
                path_commands.append(
                    f"M {p0.x():.2f},{p0.y():.2f} "
                    f"C {p1.x():.2f},{p1.y():.2f} "
                    f"{p2.x():.2f},{p2.y():.2f} "
                    f"{p3.x():.2f},{p3.y():.2f}"
                )

        if not path_commands:
            return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%"></svg>'

        # Compute bounding box of all points
        all_positions = []
        for points, _ in self.curves:
            all_positions.extend(p.pos() for p in points)
        for p in self.current_points:
            all_positions.append(p.pos())

        if all_positions:
            xs = [p.x() for p in all_positions]
            ys = [p.y() for p in all_positions]
            min_x = min(xs) - SCENE_MARGIN
            max_x = max(xs) + SCENE_MARGIN
            min_y = min(ys) - SCENE_MARGIN
            max_y = max(ys) + SCENE_MARGIN
            viewbox = f"{min_x:.2f} {min_y:.2f} {max_x - min_x:.2f} {max_y - min_y:.2f}"
        else:
            viewbox = "0 0 100 100"

        d_string = " ".join(path_commands)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" width="100%" height="100%">'
            f'<path d="{d_string}" fill="{SVG_FILL}" stroke="{SVG_STROKE_COLOR}" stroke-width="{SVG_STROKE_WIDTH}"/>'
            '</svg>'
        )

    def emit_svg(self):
        self.svgCodeChanged.emit(self.generate_svg())

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        for points, path_item in self.curves:
            for pt in points:
                self.removeItem(pt)
            self.removeItem(path_item)
        for pt in self.current_points:
            self.removeItem(pt)
        self.current_points.clear()
        self.curves.clear()
        self.selected_curve_idx = -1
        self.wip_path_item.setPath(QPainterPath())
        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()

    # ------------------------------------------------------------
    #  Access to curves for info panel
    # ------------------------------------------------------------
    def get_curve_points(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            return self.curves[curve_idx][0]
        return None

    def move_selected_point(self, curve_idx, point_idx, pos):
        points, _ = self.curves[curve_idx]
        if 0 <= point_idx < len(points):
            points[point_idx].setPos(pos)
            self.on_point_moved(curve_idx)