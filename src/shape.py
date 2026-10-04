# shape.py

class Shape:
    _next_id = 1

    def __init__(self, curves):
        self.id = Shape._next_id
        Shape._next_id += 1
        self.name = f"Shape {self.id}"
        self.curves = frozenset(curves)   # 1 (teardrop) or 2+ curves
        self.selected = False

    def set_selected(self, value):
        if self.selected == value:
            return
        self.selected = value
        for curve in self.curves:
            curve.set_shape_selected(value)