# scene/scene_io.py
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from core.settings import SVG_FILL, SVG_STROKE_WIDTH, SHAPE_BORDER_DARKEN
from scene.items.bezier_curve import BezierCurve
from collections import defaultdict
from .curve_geometry import model_curve_svg_string

import math


def _bezier_point(t, p0, p1, p2=None, p3=None):
    if p3 is not None:  # Cubic
        mt = 1 - t
        x = (mt ** 3) * p0[0] + 3 * (mt ** 2) * t * p1[0] + 3 * mt * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (mt ** 3) * p0[1] + 3 * (mt ** 2) * t * p1[1] + 3 * mt * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        return x, y
    elif p2 is not None:  # Quadratic
        mt = 1 - t
        x = (mt ** 2) * p0[0] + 2 * mt * t * p1[0] + (t ** 2) * p2[0]
        y = (mt ** 2) * p0[1] + 2 * mt * t * p1[1] + (t ** 2) * p2[1]
        return x, y
    else:  # Linear
        mt = 1 - t
        return mt * p0[0] + t * p1[0], mt * p0[1] + t * p1[1]


def _bezier_derivative(t, p0, p1, p2=None, p3=None):
    if p3 is not None:  # Cubic
        mt = 1 - t
        dx = -3 * (mt ** 2) * p0[0] + 3 * (mt ** 2 - 2 * mt * t) * p1[0] + 3 * (2 * mt * t - t ** 2) * p2[0] + 3 * (t ** 2) * p3[0]
        dy = -3 * (mt ** 2) * p0[1] + 3 * (mt ** 2 - 2 * mt * t) * p1[1] + 3 * (2 * mt * t - t ** 2) * p2[1] + 3 * (t ** 2) * p3[1]
        return dx, dy
    elif p2 is not None:  # Quadratic
        mt = 1 - t
        dx = -2 * mt * p0[0] + 2 * (mt - t) * p1[0] + 2 * t * p2[0]
        dy = -2 * mt * p0[1] + 2 * (mt - t) * p1[1] + 2 * t * p2[1]
        return dx, dy
    else:  # Linear
        return p1[0] - p0[0], p1[1] - p0[1]


def variable_width_svg_path(mc, start_width, end_width, samples=24, cap_samples=8):
    """Generate an SVG path string for a variable-width stroke envelope with rounded caps."""
    pts = [mc.extremities[0], mc.controls[0] if mc.degree >= 2 else None,
           mc.controls[1] if mc.degree == 3 else None, mc.extremities[1]]
    pts = [p for p in pts if p is not None]
    p_coords = [(p.x, p.y) for p in pts]
    left_pts, right_pts = [], []

    for i in range(samples + 1):
        t = i / samples
        x, y = _bezier_point(t, *p_coords)
        dx, dy = _bezier_derivative(t, *p_coords)
        length = math.hypot(dx, dy)
        nx, ny = (-dy / length, dx / length) if length > 0 else (0.0, 1.0)
        width = start_width + (end_width - start_width) * t
        half_width = width / 2.0
        left_pts.append((x + nx * half_width, y + ny * half_width))
        right_pts.append((x - nx * half_width, y - ny * half_width))

    # Compute tangent directions at start and end for cap orientation
    dx_start, dy_start = _bezier_derivative(0, *p_coords)
    len_start = math.hypot(dx_start, dy_start)
    tx_start, ty_start = (dx_start / len_start, dy_start / len_start) if len_start > 0 else (1.0, 0.0)

    dx_end, dy_end = _bezier_derivative(1, *p_coords)
    len_end = math.hypot(dx_end, dy_end)
    tx_end, ty_end = (dx_end / len_end, dy_end / len_end) if len_end > 0 else (1.0, 0.0)

    def angle_diff(a, b):
        return (b - a) % (2 * math.pi)

    # Start cap: semicircle from right_pts[0] to left_pts[0], bulging outward (-tangent direction)
    cx_start, cy_start = p_coords[0]
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
            px = cx_start + (start_width / 2) * math.cos(angle)
            py = cy_start + (start_width / 2) * math.sin(angle)
            cap_points_start.append((px, py))
    else:
        total_angle = angle_diff(angle_left_start, angle_right_start)
        for i in range(cap_samples + 1):
            frac = i / cap_samples
            angle = angle_right_start - total_angle * frac
            px = cx_start + (start_width / 2) * math.cos(angle)
            py = cy_start + (start_width / 2) * math.sin(angle)
            cap_points_start.append((px, py))

    # End cap: semicircle from left_pts[-1] to right_pts[-1], bulging outward (+tangent direction)
    cx_end, cy_end = p_coords[-1]
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
            px = cx_end + (end_width / 2) * math.cos(angle)
            py = cy_end + (end_width / 2) * math.sin(angle)
            cap_points_end.append((px, py))
    else:
        total_angle = angle_diff(angle_right_end, angle_left_end)
        for i in range(cap_samples + 1):
            frac = i / cap_samples
            angle = angle_left_end - total_angle * frac
            px = cx_end + (end_width / 2) * math.cos(angle)
            py = cy_end + (end_width / 2) * math.sin(angle)
            cap_points_end.append((px, py))

    # Build the closed path: left side -> end cap -> right side (reversed) -> start cap
    d = f"M {left_pts[0][0]:.2f},{left_pts[0][1]:.2f}"
    for pt in left_pts[1:]:
        d += f" L {pt[0]:.2f},{pt[1]:.2f}"
    for pt in cap_points_end:
        d += f" L {pt[0]:.2f},{pt[1]:.2f}"
    for pt in reversed(right_pts):
        d += f" L {pt[0]:.2f},{pt[1]:.2f}"
    for pt in cap_points_start:
        d += f" L {pt[0]:.2f},{pt[1]:.2f}"
    d += " Z"
    return d


def generate_svg(scene, bordered: bool = False) -> str:
    """Generate SVG with proper Z-ordering for both shapes and curves."""

    # Collect all renderable items with their Z-values
    # Each item is a tuple: (z_value, svg_string)
    items = []

    # 1) Shape fills
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        d = scene.shape_manager.shape_svg_path_string(shape)
        if not d:
            continue

        # Compute effective Z: minimum Z of constituent curves
        ui_curves = list(scene.ui_curves(shape))
        if ui_curves:
            z = min(c.zValue() for c in ui_curves)
        else:
            z = 0

        # Determine color (with optional border darkening)
        if bordered:
            fill_color = shape.color.darker(SHAPE_BORDER_DARKEN).name()
        else:
            fill_color = shape.color.name()

        items.append((z, f'<path d="{d}" fill="{fill_color}" stroke="none"/>'))

    # 2) Curve strokes (rendered individually to preserve Z-order)
    for curve in scene.curves:
        mc = scene.registry.model_curve_for(curve)
        if mc is None:
            continue

        z = curve.zValue()

        # Determine stroke color (curves in colored shapes use the shape's color)
        stroke_color = curve.color.name()
        for shape in scene.shape_manager.shapes:
            if shape.color is not None and curve in scene.ui_curves(shape):
                if bordered:
                    stroke_color = shape.color.darker(SHAPE_BORDER_DARKEN).name()
                else:
                    stroke_color = shape.color.name()
                break

        # Generate the stroke SVG based on width type
        stroke_svg = None

        if mc.start_width is not None and mc.end_width is not None:
            if mc.start_width == mc.end_width:
                # Uniform width: standard SVG stroke
                d = model_curve_svg_string(mc)
                if d:
                    stroke_svg = (
                        f'<path d="{d}" fill="{SVG_FILL}" '
                        f'stroke="{stroke_color}" stroke-width="{mc.start_width}" '
                        f'stroke-linecap="round" stroke-linejoin="round"/>'
                    )
            else:
                # Variable width: filled envelope
                d = variable_width_svg_path(mc, mc.start_width, mc.end_width)
                if d:
                    stroke_svg = f'<path d="{d}" fill="{stroke_color}" stroke="none"/>'
        else:
            # Fallback for non-stroke curves
            d = model_curve_svg_string(mc)
            if d:
                stroke_svg = (
                    f'<path d="{d}" fill="{SVG_FILL}" '
                    f'stroke="{stroke_color}" stroke-width="{SVG_STROKE_WIDTH}" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>'
                )

        if stroke_svg:
            items.append((z, stroke_svg))

    # 3) Sort all items by Z-value (lowest first = drawn first = appears behind)
    items.sort(key=lambda x: x[0])

    # 4) Build the SVG body
    body = "".join(svg for _, svg in items)

    # 5) Add the SVG header
    vb = scene.viewbox
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb.x():.2f} {vb.y():.2f} '
        f'{vb.width():.2f} {vb.height():.2f}" '
        f'width="{vb.width():.2f}" height="{vb.height():.2f}">')

    if not body:
        return header + '</svg>'
    return header + body + '</svg>'


def save_state(scene) -> dict:
#    scene.registry.sync()
    location = {}
    for ci, curve in enumerate(scene.curves):
        for pi, pt in enumerate(curve.points):
            location[id(pt)] = [ci, pi]

    links = []
    for group in scene.link_manager.groups:
        serialized = [location[id(pt)] for pt in group if id(pt) in location]
        if len(serialized) >= 2:
            links.append(serialized)

    state = {"curves": [[[round(p.model_pos().x(), 3), round(p.model_pos().y(), 3)]
                         for p in curve.points]
                        for curve in scene.curves],
             "curve_color": scene.curve_color.name(),
             "version": 3,
             "viewbox": [round(scene.viewbox.width(), 2),
                         round(scene.viewbox.height(), 2)]}

    # Curves whose points are hidden, by index.
    hidden = [i for i, c in enumerate(scene.curves) if c.points_hidden]
    if hidden:
        state["points_hidden"] = hidden


    state["curve_start_widths"] = [c.start_width for c in scene.curves]
    state["curve_end_widths"] = [c.end_width for c in scene.curves]

    shape_colors = []
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        shape_colors.append({
            "curves": sorted(scene.curves.index(c) for c in scene.ui_curves(shape)),
            "color": shape.color.name(),
        })
    if shape_colors:
        state["shapes"] = shape_colors
    if links:
        state["links"] = links
    if scene.background_image_path:
        state["background"] = scene.background_image_path
    return state


def load_state(scene, state: dict, quiet: bool = False):
    curves_data = state.get("curves", [])
    links_data = state.get("links", [])

    scene.blockSignals(True)
    try:
        scene.clear_all()

        # Viewbox first: anything that reads scene.viewbox during load
        # (background scaling) depends on the restored value.
        vb_data = state.get("viewbox")
        if isinstance(vb_data, list) and len(vb_data) == 2:
            scene.set_viewbox(float(vb_data[0]), float(vb_data[1]))

        # Set the default curve color *before* building curves, so each
        # freshly-constructed BezierCurve inherits it via __init__.
        color_str = state.get("curve_color")
        if color_str:
            scene.set_curve_color(QColor(color_str))

        start_widths = state.get("curve_start_widths", [])
        end_widths = state.get("curve_end_widths", [])

        for i, points_data in enumerate(curves_data):
            sw = start_widths[i] if i < len(start_widths) else None
            ew = end_widths[i] if i < len(end_widths) else None

            # 1. Build the UI curve
            ui_curve = _build_curve_from_points(scene, points_data, start_width=sw, end_width=ew)

            # 2. Create the Model curve via the Document
            model_curve = scene.document.add_curve(ui_curve.degree, points_data, start_width=sw, end_width=ew)

            # 3. Explicitly bind UI to Model
            scene.registry.bind(ui_curve, model_curve)
            model_points = [model_curve.extremities[0], *model_curve.controls, model_curve.extremities[1]]
            for ui_pt, model_pt in zip(ui_curve.points, model_points):
                scene.registry.bind_point(ui_pt, model_pt)

            scene.curves.append(ui_curve)

        out_of_bounds = [p for c in curves_data for p in c if not scene.artboard.contains(QPointF(p[0], p[1]))]
        if out_of_bounds:
            scene.messageLogged.emit(
                f"⚠ {len(out_of_bounds)} point(s) fall outside the current artboard "
                f"— they may be clamped on the next move")

        # Restore hidden-point flags. set_points_hidden() touches only the
        # ControlPoint visibility and the curve's own flag — safe before or
        # after link restoration.
        for ci in state.get("points_hidden", []):
            if 0 <= ci < len(scene.curves):
                scene.curves[ci].set_points_hidden(True)

        _restore_links(scene, links_data)
        scene.shape_manager.rebuild_from_links()
        _restore_shape_colors(scene, state.get("shapes", []))
        bg = state.get("background")
        if bg:
            scene.load_background_image(bg)
    finally:
        scene.blockSignals(False)

    # SVG preview must always reflect the new document — even on a quiet
    # restore triggered by undo. Only the console messages are gated.
    scene.emit_svg()
    if not quiet:
        scene.messageLogged.emit(f"Loaded {len(scene.curves)} curve(s)")
        scene.shape_manager.log_shapes()




def _restore_shape_colors(scene, shapes_data):
    if not isinstance(shapes_data, list):
        return
    for entry in shapes_data:
        if not isinstance(entry, dict):
            continue
        try:
            indices = entry["curves"]
            curves = frozenset(scene.curves[i] for i in indices)
        except (KeyError, TypeError, IndexError):
            continue
        color = QColor(entry.get("color", ""))
        if not color.isValid():
            continue
        for shape in scene.shape_manager.shapes:
            if frozenset(scene.ui_curves(shape)) == curves:
                scene.shape_manager.set_color(shape, color)
                break

def _restore_links(scene, links_data):
    if not isinstance(links_data, list):
        return
    for group_data in links_data:
        if not isinstance(group_data, list) or len(group_data) < 2:
            continue
        try:
            points = [scene.curves[ci].points[pi] for ci, pi in group_data]
        except (TypeError, ValueError, IndexError):
            continue
        # Merge consecutive points into one junction via the model.
        for i in range(len(points) - 1):
            scene.link_manager.link_points(points[i], points[i + 1])


def _build_curve_from_points(scene, points_data, start_width=None, end_width=None) -> BezierCurve:
    if not isinstance(points_data, list) or len(points_data) not in (2, 3, 4):
        raise ValueError(f"Expected 2, 3 or 4 points per curve, got {points_data!r}")
    degree = len(points_data) - 1
    curve = BezierCurve(scene, degree=degree, start_width=start_width, end_width=end_width)
    curve.committed = True
    for i, coords in enumerate(points_data):
        try:
            x, y = float(coords[0]), float(coords[1])
        except (TypeError, IndexError, ValueError):
            raise ValueError(f"Invalid point #{i}: {coords!r}")
        curve.add_point(QPointF(x, y))
    return curve