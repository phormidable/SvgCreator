# settings.py
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

# ---- Window & layout ----
CANVAS_WIDTH = 900
CANVAS_HEIGHT = 700
PREVIEW_WIDTH = 900
PREVIEW_HEIGHT = 700
CODE_EDIT_HEIGHT = 300
WINDOW_WIDTH = CANVAS_WIDTH + PREVIEW_WIDTH   # 1800
WINDOW_HEIGHT = CANVAS_HEIGHT + CODE_EDIT_HEIGHT + 50  # 1050 (approx)

# ---- Scene / viewBox ----
VIEWBOX_RECT = QRectF(-500, -500, 1000, 1000)  # (x, y, width, height)

# ---- Point colors ----
ENDPOINT_COLOR = QColor("blue")
ENDPOINT_PEN_COLOR = QColor("darkblue")
CONTROL_POINT_COLOR = QColor("yellow")
CONTROL_POINT_PEN_COLOR = QColor("darkgoldenrod")  # or "darkyellow"

# ---- Curve style ----
CURVE_PEN_COLOR = QColor("blue")
CURVE_PEN_WIDTH = 2

# ---- Export defaults ----
SVG_STROKE_COLOR = "black"
SVG_STROKE_WIDTH = 2
SVG_FILL = "none"

# ---- Point size ----
POINT_RADIUS = 6
POINT_DIAMETER = POINT_RADIUS * 2