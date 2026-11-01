# scene/scene_io.py
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from core.settings import SVG_FILL, SVG_STROKE_WIDTH, SHAPE_BORDER_DARKEN
from scene.items.bezier_curve import BezierCurve
from collections import defaultdict
from .curve_geometry import model_curve_svg_string

def generate_svg(scene, bordered: bool = False) -> str:
    scene.registry.sync()
    # 1) Fills: one <path> per colored shape.
    shape_paths = []
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        d = scene.shape_manager.shape_svg_path_string(shape)
        if d:
            shape_paths.append(f'<path d="{d}" fill="{shape.color.name()}" stroke="none"/>')

    # 2) Strokes: group curves by their effective stroke color. A curve
    #    inside a colored shape is stroked with that shape's color
    curve_color = {}
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        if bordered:
            stroke = shape.color.darker(SHAPE_BORDER_DARKEN).name()
        else:
            stroke = shape.color.name()
        for curve in scene.ui_curves(shape):
            curve_color[curve] = stroke

    by_key: dict[tuple[str, float], list[str]] = defaultdict(list)
    for curve in scene.curves:
        mc = scene.registry.model_curve_for(curve)
        if mc is None:
            continue
        d = model_curve_svg_string(mc)
        if d:
            color = curve_color.get(curve, curve.color.name())
            width = (curve.stroke_width if curve.stroke_width is not None
                     else SVG_STROKE_WIDTH)
            by_key[(color, width)].append(d)

    stroke_paths = []
    for (color, width), ds in by_key.items():
        stroke_paths.append(
            f'<path d="{" ".join(ds)}" fill="{SVG_FILL}" '
            f'stroke="{color}" stroke-width="{width}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')

    vb = scene.viewbox
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb.x():.2f} {vb.y():.2f} '
        f'{vb.width():.2f} {vb.height():.2f}" '
        f'width="{vb.width():.2f}" height="{vb.height():.2f}">')

    body = "".join(shape_paths) + "".join(stroke_paths)
    if not body:
        return header + '</svg>'
    return header + body + '</svg>'


def save_state(scene) -> dict:
    scene.registry.sync()
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

    state["curve_strokes"] = [c.stroke_width for c in scene.curves]

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

        strokes = state.get("curve_strokes", [])
        for i, points_data in enumerate(curves_data):
            w = strokes[i] if i < len(strokes) else None
            curve = _build_curve_from_points(scene, points_data, stroke_width=w)
            scene.curves.append(curve)

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


def _build_curve_from_points(scene, points_data, stroke_width=None) -> BezierCurve:
    if not isinstance(points_data, list) or len(points_data) not in (2, 3, 4):
        raise ValueError(f"Expected 2, 3 or 4 points per curve, got {points_data!r}")
    degree = len(points_data) - 1
    curve = BezierCurve(scene, degree=degree, stroke_width=stroke_width)
    curve.committed = True
    for i, coords in enumerate(points_data):
        try:
            x, y = float(coords[0]), float(coords[1])
        except (TypeError, IndexError, ValueError):
            raise ValueError(f"Invalid point #{i}: {coords!r}")
        curve.add_point(QPointF(x, y))
    return curve