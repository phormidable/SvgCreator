# scene/items/bezier_curve.py
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath, QColor, QPainter, QPen
from PySide6.QtCore import QRectF, Qt

from core.settings import CURVE_PEN_WIDTH, SHAPE_SELECTED_CURVE_PEN_WIDTH,CURVE_SELECTED_PEN_WIDTH, HOVER_TOLERANCE
from core.bezier_math import compute_variable_width_envelope,envelope_to_qt_path
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
        pts = [(p.x(), p.y()) for p in self.positions()]
        envelope = compute_variable_width_envelope(
            pts, self.start_width, self.end_width
        )
        return envelope_to_qt_path(envelope)


    def get_tight_bbox(self):
        """Returns (min_x, min_y, max_x, max_y) of the actual curve geometry.
        Cached to prevent redundant calculations during selection/centering."""
        if self._bbox is not None:
            return self._bbox

        pts = [(p.model_pos().x(), p.model_pos().y()) for p in self.points]
        self._bbox = curve_bbox(pts)
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