# presets.py
"""Preset curve/shape definitions.

A preset describes a small cluster of curves (and optional endpoint links)
that the user can place with a single click. Offsets are relative to the
placement point (the cursor).

Curves are always stored in cubic form (4 offsets: p0, c1, c2, p3).
`offsets_for_degree` adapts them to the current creation degree:
  - Cubic: use all four offsets.
  - Quadratic: keep p0, c1, p3 (drop the second control point).

For straight edges, storing c1 = c2 = midpoint keeps the cubic a straight
line and still yields a straight quadratic after the drop — so both
degrees render polygon presets identically.
"""


class CurveDef:
    def __init__(self, offsets, quadratic_offsets=None):
        # offsets: always 4 (x, y) tuples (p0, c1, c2, p3) — cubic form.
        # quadratic_offsets: optional 3-tuple (p0, c, p3). If given, used
        # verbatim for quadratic placement; otherwise, the drop rule applies
        # (keep p0, c1, p3).
        self.offsets = offsets
        self.quadratic_offsets = quadratic_offsets

    def offsets_for_degree(self, degree: int):
        if degree == 3:
            return self.offsets
        if self.quadratic_offsets is not None:
            return self.quadratic_offsets
        return [self.offsets[0], self.offsets[1], self.offsets[3]]


class PresetDef:
    def __init__(self, name, label, curves, links=None, tooltip=""):
        self.name = name
        self.label = label
        self.curves = curves
        self.links = links or []
        self.tooltip = tooltip


# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------
def _polygon_preset(name, label, verts, tooltip=""):
    """Closed polygon: one straight curve per edge, consecutive endpoints
    linked into a loop.
    Cubic: controls at 1/3 and 2/3 of the edge (so both handles are visible
    and selectable). Quadratic: single control at the midpoint."""
    n = len(verts)
    curves = []
    for i in range(n):
        ax, ay = verts[i]
        bx, by = verts[(i + 1) % n]
        c1 = ((2 * ax + bx) / 3, (2 * ay + by) / 3)
        c2 = ((ax + 2 * bx) / 3, (ay + 2 * by) / 3)
        mid = ((ax + bx) / 2, (ay + by) / 2)
        curves.append(CurveDef(
            [(ax, ay), c1, c2, (bx, by)],
            quadratic_offsets=[(ax, ay), mid, (bx, by)],
        ))
    links = [((i, -1), ((i + 1) % n, 0)) for i in range(n)]
    return PresetDef(name=name, label=label, tooltip=tooltip, curves=curves, links=links)


def _ellipse_preset(name, label, rx, ry, tooltip=""):
    """Ellipse as 4 cubic quarter-arcs."""
    k = 0.5522847498  # kappa: circular-arc control ratio
    kx, ky = rx * k, ry * k
    pts = [(rx, 0), (0, -ry), (-rx, 0), (0, ry)]   # right, top, left, bottom
    ctrls = [
        [(rx, -ky), (kx, -ry)],      # right → top
        [(-kx, -ry), (-rx, -ky)],    # top → left
        [(-rx, ky), (-kx, ry)],      # left → bottom
        [(kx, ry), (rx, ky)],        # bottom → right
    ]
    curves = []
    for i in range(4):
        a = pts[i]
        b = pts[(i + 1) % 4]
        c1, c2 = ctrls[i]
        curves.append(CurveDef([a, c1, c2, b]))
    links = [((i, -1), ((i + 1) % 4, 0)) for i in range(4)]
    return PresetDef(name=name, label=label, tooltip=tooltip, curves=curves, links=links)


# ------------------------------------------------------------
#  Presets
# ------------------------------------------------------------
PRESETS = {
    # ---- Moons ----
    "moon_up": PresetDef(
        name="moon_up", label="🌙↑",
        tooltip="Upward moon (single curve)",
        curves=[CurveDef([(-154, 104), (-128, -106), (132, -142), (149, 145)])],
    ),
    "moon_right": PresetDef(
        name="moon_right", label="🌙→",
        tooltip="Rightward moon (single curve)",
        curves=[CurveDef([(-195, -147), (187, -51), (194, 57), (-188, 140)])],
    ),
    "moon_down": PresetDef(
        name="moon_down", label="🌙↓",
        tooltip="Downward moon (single curve)",
        curves=[CurveDef([(-165, -169), (-130, 173), (117, 153), (179, -158)])],
    ),
    "moon_left": PresetDef(
        name="moon_left", label="🌙←",
        tooltip="Leftward moon (single curve)",
        curves=[CurveDef([(62, -127), (-126, -84), (-126, 108), (190, 102)])],
    ),

    # ---- Polygons ----
        "triangle": _polygon_preset(
        "triangle", "△",
        [(-80, 40), (80, 40), (0, -80)],
        tooltip="Triangle (3 curves linked into a shape)",
    ),
    "square": _polygon_preset(
        "square", "□",
        [(-50, -50), (50, -50), (50, 50), (-50, 50)],
        tooltip="Square (4 curves linked into a shape)"),
    "pentagon": _polygon_preset(
        "pentagon", "⬠",
        [(0, -60), (57, -19), (35, 49), (-35, 49), (-57, -19)],
        tooltip="Pentagon (5 curves linked into a shape)"),
    "rhombus_wide": _polygon_preset(
        "rhombus_wide", "◇",
        [(0, -30), (80, 0), (0, 30), (-80, 0)],
        tooltip="Wide rhombus (4 curves linked into a shape)"),
    "rhombus_tall": _polygon_preset(
        "rhombus_tall", "◈",
        [(0, -80), (30, 0), (0, 80), (-30, 0)],
        tooltip="Tall rhombus (4 curves linked into a shape)"),

    # ---- Ellipses ----
    "ellipse_wide": _ellipse_preset(
        "ellipse_wide", "⬭", 80, 40,
        tooltip="Wide ellipse (4 curves linked into a shape)"),
    "ellipse_tall": _ellipse_preset(
        "ellipse_tall", "⬯", 40, 80,
        tooltip="Tall ellipse (4 curves linked into a shape)"),

    # ---- Arrows ----
    "arrow_up": _polygon_preset(
        "arrow_up", "↑",
        [(-30, 40), (-30, -10), (-60, -10), (0, -60),
         (60, -10), (30, -10), (30, 40)],
        tooltip="Up arrow (7 curves linked into a shape)"),
    "arrow_right": _polygon_preset(
        "arrow_right", "→",
        [(-40, -30), (10, -30), (10, -60), (60, 0),
         (10, 60), (10, 30), (-40, 30)],
        tooltip="Right arrow (7 curves linked into a shape)"),
    "arrow_down": _polygon_preset(
        "arrow_down", "↓",
        [(-30, -40), (30, -40), (30, 10), (60, 10),
         (0, 60), (-60, 10), (-30, 10)],
        tooltip="Down arrow (7 curves linked into a shape)"),
    "arrow_left": _polygon_preset(
        "arrow_left", "←",
        [(40, -30), (-10, -30), (-10, -60), (-60, 0),
         (-10, 60), (-10, 30), (40, 30)],
        tooltip="Left arrow (7 curves linked into a shape)"),
}