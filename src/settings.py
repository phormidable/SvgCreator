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
VIEWBOX_RECT = QRectF(-500, -500, 1000, 1000)
SCENE_MARGIN = 50

# ---- Point colors ----
ENDPOINT_COLOR = QColor("blue")
ENDPOINT_PEN_COLOR = QColor("darkblue")
CONTROL_POINT_COLOR = QColor("yellow")
CONTROL_POINT_PEN_COLOR = QColor("darkgoldenrod")

# ---- Curve style ----
CURVE_PEN_COLOR = QColor("blue")
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

