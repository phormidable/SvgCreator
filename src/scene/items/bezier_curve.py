# scene/items/bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QColor, QPainter, QPen
from PySide6.QtCore import QRectF, Qt

from core.settings import CURVE_PEN_WIDTH, SHAPE_SELECTED_CURVE_PEN_WIDTH,CURVE_SELECTED_PEN_WIDTH, HOVER_TOLERANCE

from scene.items.control_point import ControlPoint
from scene.curve_geometry import curve_bbox
from scene.helpers import make_round_pen

from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from scene.bezier_scene import BezierScene


class BezierCurve(QGraphicsItem):
    _next_id = 1

    def __init__(self, scene, degree: int = 3, start_width: int | None = None, end_width: int | None = None):
        super().__init__()
        self.id = BezierCurve._next_id
        BezierCurve._next_id += 1
        self.name = f"Curve {self.id}"
        self.degree = degree
        self.start_width = start_width
        self.end_width = end_width
        self.color = QColor(scene.curve_color)

        # Use start_width for the Qt preview pen, fallback to default if not a stroke curve
        preview_width = start_width if start_width is not None else CURVE_PEN_WIDTH
        self.pen = make_round_pen(self.color, preview_width)

        self.points: list[ControlPoint] = []
        self._bbox = None  # NEW: Cache for tight bounding box
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
        scene = self.scene()
        if scene is None:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # If variable width, fill the envelope path
        if (self.start_width is not None and self.end_width is not None and
                self.start_width != self.end_width):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawPath(self._path)
        else:
            # Uniform width: use standard stroke rendering
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

    def set_color(self, color):
        self.color = QColor(color)
        width = self.start_width if self.start_width is not None else CURVE_PEN_WIDTH
        self.pen = QPen(self.color, width)
        self.pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.update()


    def set_widths(self, start_width, end_width):
        if self.start_width == start_width and self.end_width == end_width:
            return
        self.start_width = start_width
        self.end_width = end_width
        self.set_color(self.color)  # rebuild pen at new width
        self.rebuild_path()

    def rebuild_path(self):
        self.prepareGeometryChange()

        # If variable width and we have at least 2 points, generate a filled polygon envelope
        if (self.start_width is not None and self.end_width is not None and
                self.start_width != self.end_width and len(self.points) >= 2):
            self._path = self._build_variable_width_path()
            self._hit_path = self._path  # Use the same path for hit testing
        else:
            # Uniform width OR not enough points yet: use the standard stroke rendering
            preview_width = self.start_width if self.start_width is not None else CURVE_PEN_WIDTH
            self._path, self._hit_path = self._scene.curve_renderer.paths_for(
                self.positions(), self.degree, preview_width)

        self._bbox = None
        self.update()

    def _build_variable_width_path(self):
        """Generate a QPainterPath representing the variable-width envelope with rounded caps."""
        import math
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPainterPath

        positions = self.positions()
        pts = [(p.x(), p.y()) for p in positions]

        # Sample the curve and compute left/right offset points
        samples = 24
        cap_samples = 8
        left_pts, right_pts = [], []

        for i in range(samples + 1):
            t = i / samples
            x, y = self._bezier_point(t, pts)
            dx, dy = self._bezier_derivative(t, pts)
            length = math.hypot(dx, dy)
            nx, ny = (-dy / length, dx / length) if length > 0 else (0.0, 1.0)
            width = self.start_width + (self.end_width - self.start_width) * t
            half_width = width / 2.0
            left_pts.append((x + nx * half_width, y + ny * half_width))
            right_pts.append((x - nx * half_width, y - ny * half_width))

        # Compute tangent directions at start and end for cap orientation
        dx_start, dy_start = self._bezier_derivative(0, pts)
        len_start = math.hypot(dx_start, dy_start)
        tx_start, ty_start = (dx_start / len_start, dy_start / len_start) if len_start > 0 else (1.0, 0.0)

        dx_end, dy_end = self._bezier_derivative(1, pts)
        len_end = math.hypot(dx_end, dy_end)
        tx_end, ty_end = (dx_end / len_end, dy_end / len_end) if len_end > 0 else (1.0, 0.0)

        def angle_diff(a, b):
            return (b - a) % (2 * math.pi)

        # Start cap: semicircle from right_pts[0] to left_pts[0]
        cx_start, cy_start = pts[0]
        angle_right_start = math.atan2(right_pts[0][1] - cy_start, right_pts[0][0] - cx_start)
        angle_left_start = math.atan2(left_pts[0][1] - cy_start, left_pts[0][0] - cx_start)
        angle_out_start = math.atan2(-ty_start, -tx_start)

        ccw_right_to_left = angle_diff(angle_right_start, angle_left_start)
        ccw_right_to_out = angle_diff(angle_right_start, angle_out_start)

        cap_points_start = []
        if ccw_right_to_out < ccw_right_to_left:
            total_angle = ccw_right_to_left
            for i in range(cap_samples + 1):
                frac = i / cap_samples
                angle = angle_right_start + total_angle * frac
                px = cx_start + (self.start_width / 2) * math.cos(angle)
                py = cy_start + (self.start_width / 2) * math.sin(angle)
                cap_points_start.append((px, py))
        else:
            total_angle = angle_diff(angle_left_start, angle_right_start)
            for i in range(cap_samples + 1):
                frac = i / cap_samples
                angle = angle_right_start - total_angle * frac
                px = cx_start + (self.start_width / 2) * math.cos(angle)
                py = cy_start + (self.start_width / 2) * math.sin(angle)
                cap_points_start.append((px, py))

        # End cap: semicircle from left_pts[-1] to right_pts[-1]
        cx_end, cy_end = pts[-1]
        angle_left_end = math.atan2(left_pts[-1][1] - cy_end, left_pts[-1][0] - cx_end)
        angle_right_end = math.atan2(right_pts[-1][1] - cy_end, right_pts[-1][0] - cx_end)
        angle_out_end = math.atan2(ty_end, tx_end)

        ccw_left_to_right = angle_diff(angle_left_end, angle_right_end)
        ccw_left_to_out = angle_diff(angle_left_end, angle_out_end)

        cap_points_end = []
        if ccw_left_to_out < ccw_left_to_right:
            total_angle = ccw_left_to_right
            for i in range(cap_samples + 1):
                frac = i / cap_samples
                angle = angle_left_end + total_angle * frac
                px = cx_end + (self.end_width / 2) * math.cos(angle)
                py = cy_end + (self.end_width / 2) * math.sin(angle)
                cap_points_end.append((px, py))
        else:
            total_angle = angle_diff(angle_right_end, angle_left_end)
            for i in range(cap_samples + 1):
                frac = i / cap_samples
                angle = angle_left_end - total_angle * frac
                px = cx_end + (self.end_width / 2) * math.cos(angle)
                py = cy_end + (self.end_width / 2) * math.sin(angle)
                cap_points_end.append((px, py))

        # Build the closed polygon path: left side -> end cap -> right side (reversed) -> start cap
        path = QPainterPath()
        path.moveTo(left_pts[0][0], left_pts[0][1])
        for pt in left_pts[1:]:
            path.lineTo(pt[0], pt[1])
        for pt in cap_points_end:
            path.lineTo(pt[0], pt[1])
        for pt in reversed(right_pts):
            path.lineTo(pt[0], pt[1])
        for pt in cap_points_start:
            path.lineTo(pt[0], pt[1])
        path.closeSubpath()

        return path

    def _bezier_point(self, t, pts):
        """Evaluate Bezier curve at parameter t."""
        if len(pts) == 4:  # Cubic
            p0, p1, p2, p3 = pts
            mt = 1 - t
            x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
            y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
            return x, y
        elif len(pts) == 3:  # Quadratic
            p0, p1, p2 = pts
            mt = 1 - t
            x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
            y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
            return x, y
        else:  # Linear
            p0, p1 = pts
            mt = 1 - t
            return mt * p0[0] + t * p1[0], mt * p0[1] + t * p1[1]

    def _bezier_derivative(self, t, pts):
        """Evaluate Bezier curve derivative at parameter t."""
        if len(pts) == 4:  # Cubic
            p0, p1, p2, p3 = pts
            mt = 1 - t
            dx = -3 * (mt ** 2) * p0[0] + 3 * (mt ** 2 - 2 * mt * t) * p1[0] + 3 * (2 * mt * t - t ** 2) * p2[0] + 3 * (t ** 2) * p3[0]
            dy = -3 * (mt ** 2) * p0[1] + 3 * (mt ** 2 - 2 * mt * t) * p1[1] + 3 * (2 * mt * t - t ** 2) * p2[1] + 3 * (t ** 2) * p3[1]
            return dx, dy
        elif len(pts) == 3:  # Quadratic
            p0, p1, p2 = pts
            mt = 1 - t
            dx = -2 * mt * p0[0] + 2 * (mt - t) * p1[0] + 2 * t * p2[0]
            dy = -2 * mt * p0[1] + 2 * (mt - t) * p1[1] + 2 * t * p2[1]
            return dx, dy
        else:  # Linear
            p0, p1 = pts
            return p1[0] - p0[0], p1[1] - p0[1]

    def get_tight_bbox(self):
        """Returns (min_x, min_y, max_x, max_y) of the actual curve geometry.
        Cached to prevent redundant calculations during selection/centering."""
        if self._bbox is not None:
            return self._bbox

        pts = [(p.model_pos().x(), p.model_pos().y()) for p in self.points]
        self._bbox = curve_bbox(pts, self.degree)
        return self._bbox

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
        """Return (c1_pos, c2_pos, end_pt) describing a cubic that traces the
        same path as this curve, starting from `start_pt` (one of the two
        endpoints). Quadratics and lines are converted to their exact cubic
        equivalent."""
        pts = self.points
        if start_pt is pts[0]:
            ctrl = pts[1:-1]
            end = pts[-1]
        else:
            ctrl = list(reversed(pts[1:-1]))
            end = pts[0]
        p0 = start_pt.pos()
        p2 = end.pos()
        if self.degree == 3:
            return ctrl[0].pos(), ctrl[1].pos(), end
        if self.degree == 1:
            # Line as cubic: controls at 1/3 and 2/3 along the segment.
            c1 = p0 + (p2 - p0) * (1.0 / 3.0)
            c2 = p0 + (p2 - p0) * (2.0 / 3.0)
            return c1, c2, end
        # degree 2
        p1 = ctrl[0].pos()
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