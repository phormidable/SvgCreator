# scene/items/control_point.py
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem
from PySide6.QtCore import QPointF, QRectF

from core.settings import (
    POINT_DIAMETER, LINKED_RING_EXTRA, LINKED_RING_PEN_WIDTH, POINT_RADIUS, SELECTED_POINT_OUTER_WIDTH
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

    def model_pos(self) -> QPointF:
        """The authoritative position, read from the model Point. Application
        code should use this; QGraphicsItem.pos() returns the item's own
        cached Qt position, which normally matches but is not the source of
        truth."""
        scene = self.curve.scene() if self.curve is not None else None
        if scene is not None:
            mp = scene.registry.model_point_for(self)
            if mp is not None:
                return QPointF(mp.x, mp.y)
        return super().pos()

    def boundingRect(self):
        r = POINT_RADIUS
        if self.linked:
            r = max(r, POINT_RADIUS + LINKED_RING_EXTRA + LINKED_RING_PEN_WIDTH)
        if self.selected:
            r = max(r, POINT_RADIUS + SELECTED_POINT_OUTER_WIDTH)
        else:
            r = max(r, POINT_RADIUS + 1.5)  # hover/focus pen
        return QRectF(-r, -r, 2 * r, 2 * r)

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
                    mp.x = value.x()
                    mp.y = value.y()
                scene.link_manager.propagate_move(self, QPointF(value.x(), value.y()))
                self.curve.on_point_moved()
                scene.on_point_moved(self)
        return super().itemChange(change, value)