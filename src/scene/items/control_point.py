# scene/items/control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtCore import QPointF, QRectF

from core.settings import (
    POINT_DIAMETER, LINKED_RING_EXTRA, LINKED_RING_PEN_WIDTH,
)


class ControlPoint(QGraphicsEllipseItem):
    def __init__(self, pos, curve, point_idx):
        half = POINT_DIAMETER / 2
        super().__init__(-half, -half, POINT_DIAMETER, POINT_DIAMETER)
        self.setPos(pos)
        self.curve = curve
        self.point_idx = point_idx
        self.linked = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    # ---- Derived state (unchanged — reads through Selection) ----
    @property
    def selected(self):
        scene = self.curve.scene() if self.curve is not None else None
        if scene is None:
            return False
        return scene.selection.is_point_selected(self)

    @property
    def hovered(self):
        scene = self.curve.scene() if self.curve is not None else None
        if scene is None:
            return False
        return scene.selection.hovered_curve is self.curve

    @property
    def focused(self):
        scene = self.curve.scene() if self.curve is not None else None
        if scene is None:
            return False
        return scene.selection.focused_point is self

    def is_endpoint(self):
        return self.point_idx == 0 or self.point_idx == self.curve.degree

    def pos(self):
        scene = self.curve.scene() if self.curve is not None else None
        if scene is not None:
            mp = scene.registry.model_point_for(self)
            if mp is not None:
                return QPointF(mp.x, mp.y)
        return super().pos()

    def boundingRect(self):
        if self.linked:
            half = POINT_DIAMETER / 2 + LINKED_RING_EXTRA + LINKED_RING_PEN_WIDTH
            return QRectF(-half, -half, 2 * half, 2 * half)
        return super().boundingRect()

    def set_linked(self, value):
        if self.linked == value:
            return
        self.prepareGeometryChange()
        self.linked = value
        self.update()

    # ---- New: paint delegates to the renderer ----
    def paint(self, painter, option, widget=None):
        self.scene().point_renderer.draw(painter, self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene = self.curve.scene()
            if scene is None:
                return value  # no clamping possible; accept as-is
            artboard = self.curve.scene().artboard
            x = min(max(value.x(), artboard.left()), artboard.right())
            y = min(max(value.y(), artboard.top()), artboard.bottom())
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.curve.scene()
            if scene is not None:
                mp = scene.registry.model_point_for(self)
                if mp is not None:
                    p = super().pos()
                    mp.x = p.x()
                    mp.y = p.y()
                scene.link_manager.propagate_move(self, self.pos())
                self.curve.on_point_moved()
                scene.on_point_moved(self)
        return super().itemChange(change, value)