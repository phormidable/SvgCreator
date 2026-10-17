# core/presets.py
"""Preset curve/shape definitions.

A preset describes a small cluster of curves (and optional endpoint links)
that the user can place with a single click. Offsets are relative to the
placement point (the cursor).

Two curve-def types exist:
  - CurveDef:        stores cubic form (4 offsets) and adapts to the
                     toolbar degree. Quadratic drops the second control,
                     or uses an explicit quadratic_offsets override.
  - LiteralCurveDef: stores 3 or 4 points and ignores the toolbar
                     degree, keeping the degree it was saved at. Used by
                     _literal_preset for shapes pasted from user saves.

For straight edges, storing c1 = c2 = midpoint keeps the cubic a straight
line and still yields a straight quadratic after the drop — so both
degrees render polygon presets identically.
"""


class CurveDef:
    """Adapts to the toolbar degree. offsets is always 4 points."""
    def __init__(self, offsets, quadratic_offsets=None):
        self.offsets = offsets
        self.quadratic_offsets = quadratic_offsets

    def offsets_for_degree(self, degree: int):
        if degree == 3:
            return self.offsets
        if self.quadratic_offsets is not None:
            return self.quadratic_offsets
        return [self.offsets[0], self.offsets[1], self.offsets[3]]

    def for_degree(self, toolbar_degree):
        return toolbar_degree, self.offsets_for_degree(toolbar_degree)


class LiteralCurveDef:
    """Fixed at the degree it was saved. points is 3 or 4."""
    def __init__(self, points):
        if len(points) not in (3, 4):
            raise ValueError(f"Need 3 or 4 points, got {len(points)}")
        self.points = points
        self.degree = len(points) - 1

    def for_degree(self, toolbar_degree):
        # `toolbar_degree` is unused: this def always returns its own degree.
        # The parameter is required to match CurveDef's interface
        return self.degree, self.points

class PresetDef:
    def __init__(self, name, label, curves, links=None, tooltip="", category="Polygons"):
        self.name = name
        self.label = label
        self.curves = curves
        self.links = links or []
        self.tooltip = tooltip
        self.category = category



# ------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------
def _poly_preset(name, label, verts, closed, tooltip="", category="polygon"):
    """Polyline (closed=False) or polygon (closed=True): straight cubic
    curves between consecutive vertices, endpoints linked. Closed loops
    add a wrapping edge and form a shape.

    Cubic: controls at 1/3 and 2/3 of the edge (so both handles are
    visible and selectable). Quadratic: single control at the midpoint."""
    edges = list(zip(verts, verts[1:]))
    if closed:
        edges.append((verts[-1], verts[0]))

    curves = []
    for (ax, ay), (bx, by) in edges:
        c1 = ((2 * ax + bx) / 3, (2 * ay + by) / 3)
        c2 = ((ax + 2 * bx) / 3, (ay + 2 * by) / 3)
        mid = ((ax + bx) / 2, (ay + by) / 2)
        curves.append(CurveDef([(ax, ay), c1, c2, (bx, by)], quadratic_offsets=[(ax, ay), mid, (bx, by)]))

    links = [((i, -1), (i + 1, 0)) for i in range(len(curves) - 1)]
    if closed:
        links.append(((len(curves) - 1, -1), (0, 0)))

    return PresetDef(name=name, label=label, tooltip=tooltip, curves=curves, links=links, category=category)

def _literal_preset(name, label, curves, tooltip="", closed=False, category="polygon"):
    """Preset from literal curves, authored centered on the origin."""
    defs = [LiteralCurveDef(list(c)) for c in curves]

    links = []
    for i in range(len(curves) - 1):
        if _coincident(curves[i][-1], curves[i + 1][0]):
            links.append(((i, -1), (i + 1, 0)))
    if closed and len(curves) > 1:
        if _coincident(curves[-1][-1], curves[0][0]):
            links.append(((len(curves) - 1, -1), (0, 0)))

    return PresetDef(name=name, label=label, tooltip=tooltip, curves=defs, links=links, category=category)


def _coincident(a, b, tol=0.5):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def _ellipse_preset(name, label, rx, ry, tooltip="", category="curves"):
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
    # Quadratic handle: the corner of the bounding box — intersection of
    # the two endpoint tangents. Symmetric between the arc's ends.
    quad_ctrl = [(rx, -ry), (-rx, -ry), (-rx, ry), (rx, ry)]
    curves = []
    for i in range(4):
        a = pts[i]
        b = pts[(i + 1) % 4]
        c1, c2 = ctrls[i]
        curves.append(CurveDef([a, c1, c2, b], quadratic_offsets=[a, quad_ctrl[i], b]))
    links = [((i, -1), ((i + 1) % 4, 0)) for i in range(4)]
    return PresetDef(name=name, label=label, tooltip=tooltip, curves=curves, links=links, category=category)


# ------------------------------------------------------------
#  Presets
# ------------------------------------------------------------
PRESETS = {
    # ---- Polygons ----
    "triangle": _poly_preset("triangle", "△",[(-80, 40), (80, 40), (0, -80)],
                             closed=True, tooltip="Triangle pointing up", category="Polygons"),
    "square": _poly_preset("square", "□", [(-50, -50), (50, -50), (50, 50), (-50, 50)],
                           closed=True, tooltip="Square of side = 100px", category="Polygons"),
    "pentagon": _poly_preset("pentagon", "⬠", [(0, -60), (57, -19), (35, 49), (-35, 49), (-57, -19)],
                             closed=True, tooltip="Pentagon", category="Polygons"),
    "rhombus_wide": _poly_preset("rhombus_wide", "◇", [(0, -30), (80, 0), (0, 30), (-80, 0)], closed=True,
                                 tooltip="Losange - horizontal", category="Polygons"),
    "rhombus_tall": _poly_preset("rhombus_tall", "◈", [(0, -80), (30, 0), (0, 80), (-30, 0)],
                                 closed=True, tooltip="Losange - vertical", category="Polygons"),

    # ---- Ellipses ----
    "ellipse_wide": _ellipse_preset("ellipse_wide", "⬭", 80, 40, tooltip="Wide ellipse (4 curves linked into a shape)", category="Curves"),
    "ellipse_tall": _ellipse_preset("ellipse_tall", "⬯", 40, 80, tooltip="Tall ellipse (4 curves linked into a shape)", category="Curves"),

    # ---- Arrows ----
    "arrow_up": _poly_preset("arrow_up", "↑",[(-30, 40), (-30, -10), (-60, -10), (0, -60), (60, -10), (30, -10), (30, 40)],
                             closed=True, tooltip="Up arrow", category="Shapes"),
    "arrow_right": _poly_preset("arrow_right", "→",[(-40, -30), (10, -30), (10, -60), (60, 0), (10, 60), (10, 30), (-40, 30)],
                                closed=True, tooltip="Right arrow", category="Shapes"),
    "arrow_down": _poly_preset("arrow_down", "↓",[(-30, -40), (30, -40), (30, 10), (60, 10), (0, 60), (-60, 10), (-30, 10)],
                               closed=True, tooltip="Down arrow", category="Shapes"),
    "arrow_left": _poly_preset("arrow_left", "←",[(40, -30), (-10, -30), (-10, -60), (-60, 0), (-10, 60), (-10, 30), (40, 30)],
                               closed=True, tooltip="Left arrow", category="Shapes"),

    # ---- Lines ----
    "line_vertical": _poly_preset("line_vertical", "│", [(0, -50), (0, 50)], closed=False,
                                  tooltip="Vertical straight curve", category="Curves"),
    "line_horizontal": _poly_preset("line_horizontal", "─", [(-50, 0), (50, 0)], closed=False,
                                    tooltip="Horizontal straight curve", category="Curves"),

# ---- Rectangles ----
    "horizontal_rectangle": _poly_preset("horizontal_rectangle", "-",[(-120, -40), (120, -40), (120, 40), (-120, 40)],
                                         closed=True, tooltip="horizontal rectangle", category="Polygons"),
    "vertical_rectangle": _poly_preset("vertical_rectangle", "|",[(-40, -120), (40, -120), (40, 120), (-40, 120)],
                                       closed=True, tooltip="vertical rectangle", category="Polygons"),

    # ---- 'plus' sign shape (12 linked curves) ----
    "plus_sign": _poly_preset("plus_sign", "+",
        [(-120, 40),(-120, -40),(-40, -40),(-40, -120),(40, -120),(40, -40),(120, -40),(120, 40),(40, 40),(40, 120),(-40, 120),(-40, 40)],
        closed=True, tooltip="Plus sign", category="Shapes"),
    "T_shape": _poly_preset("T_shape", "T",[(-40, 120),(-40, -40),(-120, -40),(-120, -120), (120, -120), (120, -40), (40, -40), (40, 120)],
        closed = True, tooltip = "T shape", category="Shapes"),
    # ---- T shape rotations (8 linked curves each) ----
    "T_90": _poly_preset("T_90", "⊢",[(120, -40), (-40, -40), (-40, -120), (-120, -120), (-120, 120), (-40, 120), (-40, 40), (120, 40)],
        closed=True, tooltip="T shape rotated 90°", category="Shapes"),
    "T_180": _poly_preset("T_180", "⊥",[(40, -120), (40, 40), (120, 40), (120, 120), (-120, 120), (-120, 40), (-40, 40), (-40, -120)],
        closed=True, tooltip="T shape rotated 180°", category="Shapes"),
    "T_270": _poly_preset("T_270", "⊣",[(-120, -40), (40, -40), (40, -120), (120, -120), (120, 120), (40, 120), (40, 40), (-120, 40)],
        closed=True, tooltip="T shape rotated 270°", category="Shapes"),

    # ---- L shapes (2 linked curves) and rotations ----
    # Standard "L": corner bottom-left, arms up and right.
    "L": _poly_preset("L", "└", [(-50, -50), (-50, 50), (50, 50)], closed=False, tooltip="L shape (2 linked curves", category="Chains"),
    "L_90": _poly_preset("L_90", "┌", [(50, -50), (-50, -50), (-50, 50)], closed=False, tooltip="L shape rotated 90°", category="Chains"),
    "L_180": _poly_preset("L_180", "┐", [(-50, -50), (50, -50), (50, 50)], closed=False, tooltip="L shape rotated 180°", category="Chains"),
    "L_270": _poly_preset("L_270", "┘", [(50, -50), (50, 50), (-50, 50)], closed=False, tooltip="L shape rotated 270°", category="Chains"),

    # ---- Chains (open polylines) ----
    "U": _poly_preset("U", "U",[(-50, -50), (-50, 50), (50, 50), (50, -50)],closed=False, tooltip="U shape (right angles)", category="Letters"),
    "V": _poly_preset("V", "V",[(-50, -43), (0, 43), (50, -43)],closed=False, tooltip="V shape (60° angle)", category="Letters"),
    "W": _poly_preset("W", "W",[(-60, -40), (-30, 40), (0, -40), (30, 40), (60, -40)],closed=False, tooltip="W shape", category="Letters"),
    "Z": _poly_preset("Z", "Z",[(-50, -50), (50, -50), (-50, 50), (50, 50)],closed=False, tooltip="Z shape", category="Letters"),

    "C": _literal_preset(
        "C", "C",
        [
            [(60, -160), (-6.2, -160), (-60, -88.4), (-60, 0)],
            [(-60, 0), (-60, 88.4), (-6.2, 160), (60, 160)],
        ],
        tooltip="C shape (2 cubic curves)", category="Letters"),

    "S_shape": _literal_preset(
        "S_shape", "S",
        [
            [(100, -50), (100, -130), (-100, -130), (-100, -50)],
            [(-100, -50), (-100, 30), (100, -30), (100, 50)],
            [(100, 50), (100, 130), (-100, 130), (-100, 50)],
        ],
        tooltip="S shape (chain)", category="Letters"),
}