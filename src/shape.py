# shape.py

class Shape:
    _next_id = 1

    def __init__(self, curves):
        self.id = Shape._next_id
        Shape._next_id += 1
        self.name = f"Shape {self.id}"
        self.curves = frozenset(curves)   # 1 curve (teardrop) or 2 curves