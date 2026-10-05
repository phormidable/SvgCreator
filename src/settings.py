# settings.py
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

# ---- Window & layout ----
DRAWING_MIN_WIDTH = 1100
DRAWING_MIN_HEIGHT = 700

PREVIEW_WIDTH = 700
PREVIEW_HEIGHT = 700

WINDOW_WIDTH = DRAWING_MIN_WIDTH + PREVIEW_WIDTH + 15
WINDOW_HEIGHT = DRAWING_MIN_HEIGHT + 10

# ---- Scene / viewBox ----
ARTBOARD_RECT = QRectF(0, 0, 2000, 2000)
VIEWBOX_RECT = QRectF(488, 488, 1024, 1024)

# ---- Canvas colors ----
CANVAS_BACKGROUND_COLOR = QColor(170, 170, 170)    # light grey: work area
VIEWBOX_BACKGROUND_COLOR = QColor("white")         # exported area
VIEWBOX_BORDER_COLOR = QColor(120, 120, 120)
VIEWBOX_BORDER_WIDTH = 1

# ---- Hover highlight ----
HOVER_TOLERANCE = 5
HOVER_CURVE_COLOR = QColor("red")
HOVER_POINT_COLOR = QColor("red")
HOVER_POINT_PEN_COLOR = QColor("darkred")

# ---- Highlighted point colors (while dragging a curve) ----
HIGHLIGHT_POINT_COLOR = QColor("green")
HIGHLIGHT_POINT_PEN_COLOR = QColor("darkgreen")

# ---- Control point ring ----
CONTROL_POINT_RING_COLOR = QColor("yellow")
CONTROL_POINT_RING_PEN_COLOR = QColor("darkgoldenrod")

# ---- Curve style ----
CURVE_PEN_WIDTH = 2
CURVE_DRAG_PEN_COLOR = QColor("green")
CURVE_DRAG_PEN_WIDTH = 2

# ---- Export defaults ----
SVG_STROKE_COLOR = "black"
SVG_STROKE_WIDTH = 2
SVG_FILL = "none"

# ---- Point size ----
POINT_RADIUS = 6
POINT_DIAMETER = POINT_RADIUS * 2
CONTROL_POINT_INNER_RADIUS = 4

# ---- Selected point (persistent click selection) ----
SELECTED_POINT_COLOR = QColor("red")
SELECTED_POINT_PEN_COLOR = QColor("darkred")

SVG_PRECISION = 2

# ---- Linked point ring ----
LINKED_RING_COLOR = QColor("black")
LINKED_RING_PEN_WIDTH = 2
LINKED_RING_EXTRA = 2   # extra radius beyond the point's own radius

# ---- Proximity linking ----
LINK_PROXIMITY_TOLERANCE = 25        # scene units
LINK_INDICATOR_RADIUS = 10
LINK_INDICATOR_COLOR = QColor("orange")
LINK_INDICATOR_PEN_WIDTH = 2
LINK_INDICATOR_FLASH_INTERVAL = 300  # ms

# ---- Hidden curve (points hidden) ----
HIDDEN_CURVE_COLOR = QColor("grey")

# ---- Shape selection ----
SHAPE_SELECTED_CURVE_COLOR = QColor(90, 90, 90)   # mildly dark grey