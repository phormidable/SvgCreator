# presets.py
"""Preset curve/shape definitions.

A preset describes a small cluster of curves (and optional endpoint links)
that the user can place with a single click. Offsets are relative to the
placement point (the cursor).

Each preset contains:
- name:    unique key
- label:   short display string for the button
- tooltip: longer description
- curves:  list of CurveDef(offsets, degree)
- links:   list of ((curve_i, point_i), (curve_j, point_j)) tuples

When a preset is placed, curves are created and finalized, then the link
groups are applied. The result behaves exactly like hand-drawn curves.
"""


class CurveDef:
    def __init__(self, offsets):
        self.offsets = offsets

    def offsets_for_degree(self, degree: int):
        """Offsets to use at the given degree. Cubic: all four. Quadratic:
        keep p0, c1, p3 — drop the second control point."""
        if degree == 3:
            return self.offsets
        return [self.offsets[0], self.offsets[1], self.offsets[3]]


class PresetDef:
    def __init__(self, name, label, curves, links=None, tooltip=""):
        self.name = name
        self.label = label
        self.curves = curves
        self.links = links or []
        self.tooltip = tooltip


PRESETS = {
    "moon_up": PresetDef(
        name="moon_up", label="🌙↑",
        tooltip="Place an upward moon (single cubic curve)",
        curves=[CurveDef([(-154, 104), (-128, -106), (132, -142), (149, 145)])],
    ),
    "moon_right": PresetDef(
        name="moon_right", label="🌙→",
        tooltip="Place a rightward moon (single cubic curve)",
        curves=[CurveDef([(-195, -147), (187, -51), (194, 57), (-188, 140)])],
    ),
    "moon_down": PresetDef(
        name="moon_down", label="🌙↓",
        tooltip="Place a downward moon (single cubic curve)",
        curves=[CurveDef([(-165, -169), (-130, 173), (117, 153), (179, -158)])],
    ),
    "moon_left": PresetDef(
        name="moon_left", label="🌙←",
        tooltip="Place a leftward moon (single cubic curve)",
        curves=[CurveDef([(62, -127), (-126, -84), (-126, 108), (190, 102)])],
    ),
    "triangle": PresetDef(
        name="triangle", label="△",
        tooltip="Place a triangle (3 curves, linked into a shape)",
        curves=[
            # A=(-80, 40), B=(80, 40), C=(0, -80). Cubic controls at 1/3, 2/3.
            CurveDef([(-80, 40), (-27, 40), (27, 40), (80, 40)]),      # A→B
            CurveDef([(80, 40), (53, 0), (27, -40), (0, -80)]),        # B→C
            CurveDef([(0, -80), (-27, -40), (-53, 0), (-80, 40)]),     # C→A
        ],
        links=[
            # Endpoint index is -1 so this works for both degrees.
            ((0, -1), (1, 0)),   # B
            ((1, -1), (2, 0)),   # C
            ((2, -1), (0, 0)),   # A
        ],
    ),
}