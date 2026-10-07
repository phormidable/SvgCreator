# scene_io.py
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from settings import SVG_FILL, SVG_STROKE_COLOR, SVG_STROKE_WIDTH, SHAPE_BORDER_DARKEN
from bezier_curve import BezierCurve
from collections import defaultdict

def generate_svg(scene, bordered: bool = False) -> str:
    # 1) Fills: one <path> per colored shape.
    shape_paths = []
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        d = scene.shape_manager.shape_svg_path_string(shape)
        if d:
            shape_paths.append(f'<path d="{d}" fill="{shape.color.name()}" stroke="none"/>')

    # 2) Strokes: group curves by their effective stroke color. A curve
    #    inside a colored shape is stroked with that shape's color; every
    #    other curve uses the default SVG_STROKE_COLOR.
    curve_color = {}
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        if bordered:
            stroke = shape.color.darker(SHAPE_BORDER_DARKEN).name()
        else:
            stroke = shape.color.name()
        for curve in shape.curves:
            curve_color[curve] = stroke

    by_color: dict[str, list[str]] = defaultdict(list)
    for curve in scene.curves:
        d = curve.svg_path_string()
        if d:
            color = curve_color.get(curve, SVG_STROKE_COLOR)
            by_color[color].append(d)

    stroke_paths = []
    for color, ds in by_color.items():
        stroke_paths.append(
            f'<path d="{" ".join(ds)}" fill="{SVG_FILL}" '
            f'stroke="{color}" stroke-width="{SVG_STROKE_WIDTH}"/>')

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
    location = {}
    for ci, curve in enumerate(scene.curves):
        for pi, pt in enumerate(curve.points):
            location[id(pt)] = [ci, pi]

    links = []
    for group in scene.link_manager.groups:
        serialized = [location[id(pt)] for pt in group if id(pt) in location]
        if len(serialized) >= 2:
            links.append(serialized)

    state = {
        "version": 2,
        "curves": [[[round(p.x(), 3), round(p.y(), 3)] for p in curve.points] for curve in scene.curves],
    }
    shape_colors = []
    for shape in scene.shape_manager.shapes:
        if shape.color is None:
            continue
        shape_colors.append({
            "curves": sorted(scene.curves.index(c) for c in shape.curves),
            "color": shape.color.name(),
        })
    if shape_colors:
        state["shapes"] = shape_colors
    if links:
        state["links"] = links
    if scene.background_image_path:
        state["background"] = scene.background_image_path
    return state


def load_state(scene, state: dict):
    curves_data = state.get("curves", [])
    links_data = state.get("links", [])

    scene.blockSignals(True)
    try:
        scene.clear_all()
        for points_data in curves_data:
            curve = _build_curve_from_points(scene, points_data)
            scene.curves.append(curve)
        scene.selected_curve_idx = len(scene.curves) - 1 if scene.curves else -1

        _restore_links(scene, links_data)
        scene.shape_manager.rebuild_from_links()
        _restore_shape_colors(scene, state.get("shapes", []))
        bg = state.get("background")
        if bg:
            scene.load_background_image(bg)
    finally:
        scene.blockSignals(False)

    scene.emit_svg()
    scene.messageLogged.emit(f"Loaded {len(scene.curves)} curve(s)")
    scene.shape_manager.log_shapes()
    scene.pointsChanged.emit()
    scene.curveListChanged.emit()


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
            if shape.curves == curves:
                scene.shape_manager.set_color(shape, color)
                break

def _restore_links(scene, links_data):
    if not isinstance(links_data, list):
        return
    for group_data in links_data:
        if not isinstance(group_data, list):
            continue
        try:
            group = [scene.curves[ci].points[pi] for ci, pi in group_data]
        except (TypeError, ValueError, IndexError):
            continue
        if len(group) >= 2:
            scene.link_manager.groups.append(group)
            for pt in group:
                pt.set_linked(True)


def _build_curve_from_points(scene, points_data) -> BezierCurve:
    if not isinstance(points_data, list) or len(points_data) not in (3, 4):
        raise ValueError(f"Expected 3 or 4 points per curve, got {points_data!r}")
    degree = len(points_data) - 1
    curve = BezierCurve(scene, degree=degree)
    curve.committed = True
    for i, coords in enumerate(points_data):
        try:
            x, y = float(coords[0]), float(coords[1])
        except (TypeError, IndexError, ValueError):
            raise ValueError(f"Invalid point #{i}: {coords!r}")
        curve.add_point(QPointF(x, y))
    return curve