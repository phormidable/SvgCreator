# scene/helpers.py
from PySide6.QtGui import QPen
from PySide6.QtCore import Qt

def make_round_pen(color, width) -> QPen:
    """Create a QPen with round caps and joins — the house style."""
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen