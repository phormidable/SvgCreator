# control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtGui import QBrush, QPen
from settings import  POINT_DIAMETER, ENDPOINT_COLOR, ENDPOINT_PEN_COLOR, CONTROL_POINT_COLOR, CONTROL_POINT_PEN_COLOR

class ControlPoint(QGraphicsEllipseItem):
    def __init__(self, pos, scene_ref, index):
        # Circle centered at (0,0) with diameter POINT_DIAMETER
        half = POINT_DIAMETER / 2
        super().__init__(-half, -half, POINT_DIAMETER, POINT_DIAMETER)
        self.setPos(pos)

        # Assign colors based on index
        if index == 0 or index == 3:
            self.setBrush(QBrush(ENDPOINT_COLOR))
            self.setPen(QPen(ENDPOINT_PEN_COLOR, 1.5))
        else:
            self.setBrush(QBrush(CONTROL_POINT_COLOR))
            self.setPen(QPen(CONTROL_POINT_PEN_COLOR, 1.5))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.scene_ref = scene_ref

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            self.scene_ref.on_point_moved()
        return super().itemChange(change, value)