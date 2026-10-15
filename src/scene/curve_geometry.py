# scene/curve_geometry.py
"""Pure geometry of a Bezier curve. No Qt items, no scene state.

Inputs are (x, y) tuples so the module works equally well with model
Points and with QPointF.
"""

from core.settings import SVG_PRECISION

def svg_string_from_points(pts, degree: int) -> str:
    p = SVG_PRECISION
    if degree == 2:
        (x0, y0), (x1, y1), (x2, y2) = pts
        return (f"M {x0:.{p}f},{y0:.{p}f} "
                f"Q {x1:.{p}f},{y1:.{p}f} "
                f"{x2:.{p}f},{y2:.{p}f}")
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    return (f"M {x0:.{p}f},{y0:.{p}f} "
            f"C {x1:.{p}f},{y1:.{p}f} "
            f"{x2:.{p}f},{y2:.{p}f} "
            f"{x3:.{p}f},{y3:.{p}f}")

def curve_points(curve):
    """P0, [C1, [C2]], P1 as model Points, in geometric order."""
    return [curve.extremities[0], *curve.controls, curve.extremities[1]]


def model_curve_svg_string(curve) -> str:
    pts = [(p.x, p.y) for p in curve_points(curve)]
    return svg_string_from_points(pts, curve.degree)