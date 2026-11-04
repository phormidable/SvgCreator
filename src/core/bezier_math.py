"""Pure-math helpers for Bezier curves and variable-width envelopes.

No Qt dependency — can be imported from anywhere, including tests.
"""

import math


# ------------------------------------------------------------
#  Bezier evaluation
# ------------------------------------------------------------

def bezier_point(t, pts):
    """Evaluate a Bezier curve at parameter t ∈ [0, 1].

    `pts` is a list of (x, y) control points. Length determines the degree:
      2 → linear, 3 → quadratic, 4 → cubic.
    """
    n = len(pts)
    if n == 2:
        p0, p1 = pts
        mt = 1 - t
        return (mt * p0[0] + t * p1[0], mt * p0[1] + t * p1[1])
    if n == 3:
        p0, p1, p2 = pts
        mt = 1 - t
        return (
            mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
            mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1],
        )
    if n == 4:
        p0, p1, p2, p3 = pts
        mt = 1 - t
        mt2 = mt * mt
        t2 = t * t
        return (
            mt2 * mt * p0[0] + 3 * mt2 * t * p1[0] + 3 * mt * t2 * p2[0] + t2 * t * p3[0],
            mt2 * mt * p0[1] + 3 * mt2 * t * p1[1] + 3 * mt * t2 * p2[1] + t2 * t * p3[1],
        )
    raise ValueError(f"Unsupported Bezier degree: {n - 1} (need 2, 3 or 4 points)")


def bezier_derivative(t, pts):
    """Evaluate the derivative (tangent vector) of a Bezier curve at t."""
    n = len(pts)
    if n == 2:
        p0, p1 = pts
        return (p1[0] - p0[0], p1[1] - p0[1])
    if n == 3:
        p0, p1, p2 = pts
        mt = 1 - t
        return (
            -2 * mt * p0[0] + 2 * (mt - t) * p1[0] + 2 * t * p2[0],
            -2 * mt * p0[1] + 2 * (mt - t) * p1[1] + 2 * t * p2[1],
        )
    if n == 4:
        p0, p1, p2, p3 = pts
        mt = 1 - t
        mt2 = mt * mt
        t2 = t * t
        return (
            -3 * mt2 * p0[0] + 3 * (mt2 - 2 * mt * t) * p1[0]
            + 3 * (2 * mt * t - t2) * p2[0] + 3 * t2 * p3[0],
            -3 * mt2 * p0[1] + 3 * (mt2 - 2 * mt * t) * p1[1]
            + 3 * (2 * mt * t - t2) * p2[1] + 3 * t2 * p3[1],
        )
    raise ValueError(f"Unsupported Bezier degree: {n - 1}")


# ------------------------------------------------------------
#  Variable-width envelope geometry
# ------------------------------------------------------------

def compute_variable_width_envelope(pts, start_width, end_width,
                                    samples=24, cap_samples=8):
    """Compute the raw geometry of a variable-width stroke envelope.

    Returns a dict with keys:
        left_pts, right_pts, cap_points_start, cap_points_end
    Each value is a list of (x, y) tuples.

    `pts` is a list of (x, y) control points (2, 3 or 4).
    """
    left_pts, right_pts = [], []

    for i in range(samples + 1):
        t = i / samples
        x, y = bezier_point(t, pts)
        dx, dy = bezier_derivative(t, pts)
        length = math.hypot(dx, dy)
        if length > 0:
            nx, ny = -dy / length, dx / length
        else:
            nx, ny = 0.0, 1.0
        width = start_width + (end_width - start_width) * t
        half = width / 2.0
        left_pts.append((x + nx * half, y + ny * half))
        right_pts.append((x - nx * half, y - ny * half))

    # Tangent directions at start and end for cap orientation
    dx_s, dy_s = bezier_derivative(0, pts)
    len_s = math.hypot(dx_s, dy_s)
    tx_s, ty_s = (dx_s / len_s, dy_s / len_s) if len_s > 0 else (1.0, 0.0)

    dx_e, dy_e = bezier_derivative(1, pts)
    len_e = math.hypot(dx_e, dy_e)
    tx_e, ty_e = (dx_e / len_e, dy_e / len_e) if len_e > 0 else (1.0, 0.0)

    cap_points_start = _semicircle_cap(
        center=pts[0],
        radius=start_width / 2.0,
        from_pt=right_pts[0],
        to_pt=left_pts[0],
        outward_dir=(-tx_s, -ty_s),
        cap_samples=cap_samples,
    )
    cap_points_end = _semicircle_cap(
        center=pts[-1],
        radius=end_width / 2.0,
        from_pt=left_pts[-1],
        to_pt=right_pts[-1],
        outward_dir=(tx_e, ty_e),
        cap_samples=cap_samples,
    )

    return {
        "left_pts": left_pts,
        "right_pts": right_pts,
        "cap_points_start": cap_points_start,
        "cap_points_end": cap_points_end,
    }


def _semicircle_cap(center, radius, from_pt, to_pt, outward_dir, cap_samples):
    """Generate points along the semicircular cap that bulges in `outward_dir`.

    Picks the shorter arc between `from_pt` and `to_pt` that passes through
    the outward direction.
    """
    cx, cy = center
    angle_from = math.atan2(from_pt[1] - cy, from_pt[0] - cx)
    angle_to = math.atan2(to_pt[1] - cy, to_pt[0] - cx)
    angle_out = math.atan2(outward_dir[1], outward_dir[0])

    def angle_diff(a, b):
        return (b - a) % (2 * math.pi)

    ccw_from_to = angle_diff(angle_from, angle_to)
    ccw_from_out = angle_diff(angle_from, angle_out)

    points = []
    if ccw_from_out < ccw_from_to:
        total = ccw_from_to
        for i in range(cap_samples + 1):
            frac = i / cap_samples
            angle = angle_from + total * frac
            points.append((cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle)))
    else:
        total = angle_diff(angle_to, angle_from)
        for i in range(cap_samples + 1):
            frac = i / cap_samples
            angle = angle_from - total * frac
            points.append((cx + radius * math.cos(angle),
                           cy + radius * math.sin(angle)))
    return points


# ------------------------------------------------------------
#  Output formatters
# ------------------------------------------------------------

def envelope_to_svg_path(envelope):
    """Convert an envelope dict (from compute_variable_width_envelope) to an SVG `d` string."""
    left = envelope["left_pts"]
    right = envelope["right_pts"]
    cap_start = envelope["cap_points_start"]
    cap_end = envelope["cap_points_end"]

    parts = [f"M {left[0][0]:.2f},{left[0][1]:.2f}"]
    for x, y in left[1:]:
        parts.append(f"L {x:.2f},{y:.2f}")
    for x, y in cap_end:
        parts.append(f"L {x:.2f},{y:.2f}")
    for x, y in reversed(right):
        parts.append(f"L {x:.2f},{y:.2f}")
    for x, y in cap_start:
        parts.append(f"L {x:.2f},{y:.2f}")
    parts.append("Z")
    return " ".join(parts)


def envelope_to_qt_path(envelope):
    """Convert an envelope dict to a QPainterPath (closed polygon)."""
    from PySide6.QtGui import QPainterPath

    left = envelope["left_pts"]
    right = envelope["right_pts"]
    cap_start = envelope["cap_points_start"]
    cap_end = envelope["cap_points_end"]

    path = QPainterPath()
    path.moveTo(left[0][0], left[0][1])
    for x, y in left[1:]:
        path.lineTo(x, y)
    for x, y in cap_end:
        path.lineTo(x, y)
    for x, y in reversed(right):
        path.lineTo(x, y)
    for x, y in cap_start:
        path.lineTo(x, y)
    path.closeSubpath()
    return path