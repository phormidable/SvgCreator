# bezier_scene.py
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItem
from PySide6.QtCore import Signal, Qt, QRectF

from settings import VIEWBOX_RECT, SCENE_MARGIN, SVG_STROKE_COLOR, SVG_STROKE_WIDTH, SVG_FILL
from control_point import ControlPoint
from bezier_curve import BezierCurve

class BezierScene(QGraphicsScene):
    svgCodeChanged = Signal(str)
    pointsChanged = Signal()
    curveListChanged = Signal()

    def __init__(self):
        super().__init__()
        self.curves = []              # committed BezierCurve objects
        self.pending_curve = None     # BezierCurve currently being placed
        self.mode = "create"
        self.selected_curve_idx = -1
        self.dragging_curve = None    # BezierCurve currently being dragged

        self.setSceneRect(VIEWBOX_RECT)

    # ------------------------------------------------------------
    #  Mouse interaction
    # ------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.scenePos(), self.views()[0].transform())

            if isinstance(item, ControlPoint):
                curve = item.curve
                if curve.committed:
                    self.dragging_curve = curve
                    curve.set_highlighted(True)
                super().mousePressEvent(event)
                return

            if self.mode == "create":
                if self.pending_curve is None:
                    self.pending_curve = BezierCurve(self)
                self.pending_curve.add_point(event.scenePos())
                if self.pending_curve.is_complete():
                    self.finalize_curve()
                return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging_curve is not None:
                self.dragging_curve.set_highlighted(False)
                self.dragging_curve = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------
    #  Curve finalization
    # ------------------------------------------------------------
    def finalize_curve(self):
        curve = self.pending_curve
        self.pending_curve = None
        curve.committed = True
        for pt in curve.points:
            pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        curve.rebuild_path()
        self.curves.append(curve)
        self.selected_curve_idx = len(self.curves) - 1
        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()

    # ------------------------------------------------------------
    #  Change notification from a curve
    # ------------------------------------------------------------
    def on_curve_changed(self):
        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Dynamic scene rect
    # ------------------------------------------------------------
    def update_scene_rect(self):
        all_positions = []
        for curve in self.curves:
            all_positions.extend(curve.positions())
        if self.pending_curve is not None:
            all_positions.extend(self.pending_curve.positions())

        if not all_positions:
            self.setSceneRect(VIEWBOX_RECT)
            return

        xs = [p.x() for p in all_positions]
        ys = [p.y() for p in all_positions]
        min_x = min(xs) - SCENE_MARGIN
        max_x = max(xs) + SCENE_MARGIN
        min_y = min(ys) - SCENE_MARGIN
        max_y = max(ys) + SCENE_MARGIN

        rect = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        rect = rect.united(VIEWBOX_RECT)  # never smaller than the default view
        self.setSceneRect(rect)

    # ------------------------------------------------------------
    #  SVG generation
    # ------------------------------------------------------------
    def generate_svg(self):
        path_commands = []
        all_positions = []
        for curve in self.curves:
            d = curve.svg_path_string()
            if d:
                path_commands.append(d)
                all_positions.extend(curve.positions())

        if not path_commands:
            return (
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'viewBox="0 0 100 100" width="100%" height="100%"></svg>'
            )

        xs = [p.x() for p in all_positions]
        ys = [p.y() for p in all_positions]
        min_x = min(xs) - SCENE_MARGIN
        max_x = max(xs) + SCENE_MARGIN
        min_y = min(ys) - SCENE_MARGIN
        max_y = max(ys) + SCENE_MARGIN
        viewbox = f"{min_x:.2f} {min_y:.2f} {max_x - min_x:.2f} {max_y - min_y:.2f}"

        d_string = " ".join(path_commands)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
            f'width="100%" height="100%">'
            f'<path d="{d_string}" fill="{SVG_FILL}" '
            f'stroke="{SVG_STROKE_COLOR}" stroke-width="{SVG_STROKE_WIDTH}"/>'
            '</svg>'
        )

    def emit_svg(self):
        self.svgCodeChanged.emit(self.generate_svg())

    # ------------------------------------------------------------
    #  Discard incomplete curve
    # ------------------------------------------------------------
    def discard_current_points(self):
        if self.pending_curve is None:
            return
        self.pending_curve.dispose()
        self.pending_curve = None
        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()

    # ------------------------------------------------------------
    #  Clear everything
    # ------------------------------------------------------------
    def clear_all(self):
        if self.pending_curve is not None:
            self.pending_curve.dispose()
            self.pending_curve = None
        for curve in self.curves:
            curve.dispose()
        self.curves.clear()

        self.selected_curve_idx = -1
        self.dragging_curve = None

        self.update_scene_rect()
        self.emit_svg()
        self.pointsChanged.emit()
        self.curveListChanged.emit()

    # ------------------------------------------------------------
    #  Access to curves for info panel
    # ------------------------------------------------------------
    def get_curve_points(self, curve_idx):
        if 0 <= curve_idx < len(self.curves):
            return self.curves[curve_idx].points
        return None

    def move_selected_point(self, curve_idx, point_idx, pos):
        if 0 <= curve_idx < len(self.curves):
            self.curves[curve_idx].move_point(point_idx, pos)