# scene_io.py
from PySide6.QtCore import QPointF

from settings import SVG_FILL, SVG_STROKE_COLOR, SVG_STROKE_WIDTH
from bezier_curve import BezierCurve


def generate_svg(scene) -> str:
    path_commands = []
    for curve in scene.curves:
        d = curve.svg_path_string()
        if d:
            path_commands.append(d)

    vb = scene.viewbox
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb.x():.2f} {vb.y():.2f} '
        f'{vb.width():.2f} {vb.height():.2f}" '
        f'width="{vb.width():.2f}" height="{vb.height():.2f}">'
    )

    if not path_commands:
        return header + '</svg>'

    d_string = " ".join(path_commands)
    return (
        header
        + f'<path d="{d_string}" fill="{SVG_FILL}" '
          f'stroke="{SVG_STROKE_COLOR}" '
          f'stroke-width="{SVG_STROKE_WIDTH}"/>'
          '</svg>'
    )


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
        "curves": [
            [[round(p.x(), 3), round(p.y(), 3)] for p in curve.points]
            for curve in scene.curves
        ],
    }
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
        scene.rebuild_shapes_from_links()

        bg = state.get("background")
        if bg:
            scene.load_background_image(bg)
    finally:
        scene.blockSignals(False)

    scene.emit_svg()
    scene.messageLogged.emit(f"Loaded {len(scene.curves)} curve(s)")
    scene.pointsChanged.emit()
    scene.curveListChanged.emit()


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
    if not isinstance(points_data, list) or len(points_data) != 4:
        raise ValueError(f"Expected 4 points per curve, got {points_data!r}")
    curve = BezierCurve(scene)
    curve.committed = True
    for i, coords in enumerate(points_data):
        try:
            x, y = float(coords[0]), float(coords[1])
        except (TypeError, IndexError, ValueError):
            raise ValueError(f"Invalid point #{i}: {coords!r}")
        curve.add_point(QPointF(x, y))
    return curve