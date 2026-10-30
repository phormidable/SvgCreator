# scene/curve_geometry.py
"""Pure geometry of a Bezier curve. No Qt items, no scene state.

Inputs are (x, y) tuples so the module works equally well with model
Points and with QPointF.
"""

from core.settings import SVG_PRECISION

def svg_string_from_points(pts, degree: int) -> str:
    p = SVG_PRECISION
    if degree == 1:
        (x0, y0), (x1, y1) = pts
        return f"M {x0:.{p}f},{y0:.{p}f} L {x1:.{p}f},{y1:.{p}f}"
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

# scene/curve_geometry.py
"""...existing docstring..."""


def curve_bbox(points, degree):
    """Tight bounding box of the actual Bezier curve — endpoints plus the
    interior extrema where B'(t) = 0 on either axis.

    points: [(x, y), ...] in geometric order. degree 2 or 3.
    Returns (min_x, min_y, max_x, max_y).
    """
    pts = [(float(x), float(y)) for x, y in points]
    xs = [pts[0][0], pts[-1][0]]
    ys = [pts[0][1], pts[-1][1]]

    for t in _extrema_ts(pts, degree):
        x, y = _evaluate(pts, degree, t)
        xs.append(x)
        ys.append(y)

    return min(xs), min(ys), max(xs), max(ys)


def _extrema_ts(pts, degree):
    """Parameter values in (0, 1) where B'(t) = 0 along either axis."""
    if degree <= 1:
        return set()
    result = set()
    if degree == 2:
        p0, p1, p2 = pts
        for axis in (0, 1):
            denom = p0[axis] - 2 * p1[axis] + p2[axis]
            if abs(denom) < 1e-12:
                continue
            t = (p0[axis] - p1[axis]) / denom
            if 0.0 < t < 1.0:
                result.add(t)
    else:  # degree 3: a*t² + b*t + c = 0, per axis
        p0, p1, p2, p3 = pts
        for axis in (0, 1):
            a = 3 * (-p0[axis] + 3 * p1[axis] - 3 * p2[axis] + p3[axis])
            b = 6 * (p0[axis] - 2 * p1[axis] + p2[axis])
            c = 3 * (p1[axis] - p0[axis])
            for t in _solve_quadratic(a, b, c):
                if 0.0 < t < 1.0:
                    result.add(t)
    return result


def _solve_quadratic(a, b, c):
    """Real roots of a*t² + b*t + c = 0. Empty list if degenerate."""
    if abs(a) < 1e-12:
        return [] if abs(b) < 1e-12 else [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    sq = disc ** 0.5
    return [(-b + sq) / (2 * a), (-b - sq) / (2 * a)]


def _evaluate(pts, degree, t):
    """Point on the Bezier at parameter t."""
    u = 1.0 - t
    if degree == 1:
        (x0, y0), (x1, y1) = pts
        return u * x0 + t * x1, u * y0 + t * y1
    if degree == 2:
        (x0, y0), (x1, y1), (x2, y2) = pts
        return (u * u * x0 + 2 * u * t * x1 + t * t * x2,
                u * u * y0 + 2 * u * t * y1 + t * t * y2)
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    uu, tt = u * u, t * t
    return (uu * u * x0 + 3 * uu * t * x1 + 3 * u * tt * x2 + tt * t * x3,
            uu * u * y0 + 3 * uu * t * y1 + 3 * u * tt * y2 + tt * t * y3)