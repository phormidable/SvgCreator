# shape.py

class Shape:
    def __init__(self, curves):
        self.name = ""            # set by ShapeManager.refresh
        self.curves = frozenset(curves)
        self.color = None
        self.fill_item = None

