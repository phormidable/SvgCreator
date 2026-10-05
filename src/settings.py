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
HOVER_CURVE_COLOR = QColor("green")
HOVER_POINT_COLOR = QColor("green")
HOVER_POINT_PEN_COLOR = QColor("darkred")

# ---- Highlighted point colors (while dragging a curve) ----
HIGHLIGHT_POINT_COLOR = QColor("green")
HIGHLIGHT_POINT_PEN_COLOR = QColor("darkgreen")

# ---- Curve style ----
CURVE_PEN_WIDTH = 2
CURVE_DRAG_PEN_COLOR = QColor("green")
CURVE_DRAG_PEN_WIDTH = 2

# ---- Export defaults ----
SVG_STROKE_COLOR = "black"
SVG_STROKE_WIDTH = 2
SVG_FILL = "none"

# ---- Selected point (persistent click selection) ----
SELECTED_POINT_COLOR = QColor("red")
SELECTED_POINT_PEN_COLOR = QColor("darkred")
SELECTED_POINT_OUTER_COLOR = QColor("green")
SELECTED_POINT_OUTER_WIDTH = 5.0

SVG_PRECISION = 2

# ---- Proximity linking ----
LINK_PROXIMITY_TOLERANCE = 25        # scene units
LINK_INDICATOR_RADIUS = 10
LINK_INDICATOR_COLOR = QColor("orange")
LINK_INDICATOR_PEN_WIDTH = 2
LINK_INDICATOR_FLASH_INTERVAL = 300  # ms

# ---- Hidden curve (points hidden) ----
HIDDEN_CURVE_COLOR = QColor("grey")



# NEW COLORS #
# ---- Curve color ----
DEFAULT_CURVE_COLOR = QColor(90, 90, 90)

# ---- Whole-curve selection (via 'A' on hover) ----
CURVE_SELECTED_PEN_COLOR = QColor(200, 0, 0)
CURVE_SELECTED_PEN_WIDTH = 3

# ---- Point size ----
POINT_RADIUS = 8
POINT_DIAMETER = POINT_RADIUS * 2          # was 12, now 16

# ---- Point blue (endpoints + control-point outer ring) ----
POINT_BLUE = QColor.fromHsvF(0.55, 0.75, 0.85)

# ---- Endpoint appearance ----
ENDPOINT_ALPHA = 170                        # 0..255; semi-transparent fill
ENDPOINT_PEN_COLOR = QColor(30, 60, 120)

# ---- Control point rings (inside -> outside) ----
CONTROL_POINT_INNER_RADIUS = 4              # yellow
CONTROL_POINT_MIDDLE_RADIUS = 6             # white
CONTROL_POINT_INNER_COLOR = QColor("yellow")
CONTROL_POINT_MIDDLE_COLOR = QColor("white")
CONTROL_POINT_MIDDLE_PEN_COLOR = QColor("grey")
CONTROL_POINT_OUTER_PEN_COLOR = QColor(30, 60, 120)

# ---- Linked ring ----
LINKED_RING_COLOR = QColor("black")
LINKED_RING_PEN_WIDTH = 2
LINKED_RING_EXTRA = 4                       # was 2

# ---- Shape selection ----
SHAPE_SELECTED_CURVE_COLOR = QColor(200, 0, 0)
SHAPE_SELECTED_CURVE_PEN_WIDTH = 5
SHAPE_BORDER_DARKEN = 130   # QColor.darker(factor); 100 = unchanged