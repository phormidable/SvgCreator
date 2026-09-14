# settings.py
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

# ---- Window & layout ----
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 700
PREVIEW_WIDTH = 900
PREVIEW_HEIGHT = 700
INFO_HEIGHT = 150
CODE_EDIT_HEIGHT = 150
WINDOW_WIDTH = CANVAS_WIDTH + PREVIEW_WIDTH          # 1800
WINDOW_HEIGHT = CANVAS_HEIGHT + INFO_HEIGHT + CODE_EDIT_HEIGHT + 50   # 1050

# ---- Scene / viewBox ----
ARTBOARD_RECT = QRectF(-1000, -1000, 2000, 2000)
VIEWBOX_RECT = QRectF(-500, -500, 1000, 1000)

# ---- Canvas colors ----
CANVAS_BACKGROUND_COLOR = QColor(230, 230, 230)    # light grey: work area
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
