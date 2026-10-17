# core/settings.py
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor

from pathlib import Path
USER_SHAPES_PATH = Path(__file__).resolve().parent.parent / "user_shape.txt"

# ---- Zoom levels (used by the drawing view and the preview) ----
ZOOM_LEVELS = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0), ("8x", 8.0), ("16x", 16.0)]
# ---- UI: checked-toolbar-button style ----
TOOLBAR_CHECKED_STYLE = "QToolButton:checked { background-color: #cc3333; color: white; }"

PREVIEW_FIT_MARGIN = 40   # rough allowance for the preview toolbar + borders

# ---- Grid ----
GRID_MINOR_COLOR = QColor(0, 0, 0, 40)
GRID_MAJOR_COLOR = QColor(0, 0, 0, 90)
GRID_SIZE_OPTIONS = [("1px", 1), ("10px", 10), ("100px", 100)]
GRID_DEFAULT_SPACING = 10
GRID_MAJOR_EVERY = 10                # every Nth line is drawn as a major line
GRID_MIN_DEVICE_SPACING = 3          # skip drawing below this on-screen spacing
GRID_Z = -40

# ---- Window & layout ----
DRAWING_MIN_WIDTH = 1100
DRAWING_MIN_HEIGHT = 700

# Preview: fixed width for the right column; the *view* inside it is
# kept square via PreviewWidget.heightForWidth(). So PREVIEW_WIDTH is
# effectively both the column width and the minimum side of the square
# viewport — changing it below 300 would break the intent, not the layout.
PREVIEW_WIDTH = 626
PREVIEW_HEIGHT = 670

PRESET_PANEL_HEIGHT = 120
CONSOLE_HEIGHT = 100

# ---- Origin marker ----
ORIGIN_MARKER_COLOR = QColor(0, 0, 0, 180)   # mostly opaque black
ORIGIN_MARKER_PEN_WIDTH = 1
ORIGIN_MARKER_ARM = 6          # half-length of each arm, device pixels
ORIGIN_MARKER_Z = -35          # above grid (-40), below shape fills (-10)

WINDOW_WIDTH = DRAWING_MIN_WIDTH + PREVIEW_WIDTH + 15
WINDOW_HEIGHT = DRAWING_MIN_HEIGHT + 10

# ---- Scene / viewBox ----
ARTBOARD_RECT = QRectF(-1000, -1000, 2000, 2000)
VIEWBOX_RECT = QRectF(-512, -512, 1024, 1024)

# ---- Canvas colors ----
CANVAS_BACKGROUND_COLOR = QColor(170, 170, 170)    # light grey: work area
VIEWBOX_BACKGROUND_COLOR = QColor("white")         # exported area
VIEWBOX_BORDER_COLOR = QColor(120, 120, 120)
VIEWBOX_BORDER_WIDTH = 1

# ---- Hover highlight ----
HOVER_TOLERANCE = 10
HOVER_COLOR = QColor("green")
HOVER_COLOR_FOCUS = QColor("cyan")
HOVER_POINT_PEN_COLOR = QColor("darkred")

# ---- Curve style ----
CURVE_PEN_WIDTH = 2

# ---- Snap-to-grid indicator ----
SNAP_INDICATOR_RADIUS = 2
SNAP_INDICATOR_COLOR = QColor("red")
SNAP_INDICATOR_Z = 900        # above curves, below the link indicator (z=1000)

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
# ---- Transparency mode (selected shape) ----
SHAPE_TRANSPARENT_OPACITY = 0.25

# ---- Rotation ----
ROTATION_PIVOT_RADIUS = 4
ROTATION_PIVOT_COLOR = QColor("orange")