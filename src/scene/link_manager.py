# link_manager.py
"""LinkManager: owns the link groups that snap control points together,
plus the flashing proximity indicator shown while dragging a point near
a potential link target.

A link group is a list of ControlPoint that stay coincident and move as
one. Groups with fewer than 2 members are dissolved.

Owned state: groups, _propagating, _proximity_target, indicator.
"""

from core.settings import LINK_PROXIMITY_TOLERANCE
from scene.items.link_indicator import LinkIndicator


class LinkManager:
    def __init__(self, scene):
        self.scene = scene
        self._propagating = False
        self._proximity_target = None
        self.indicator = LinkIndicator()
        scene.addItem(self.indicator)

    def group_of(self, point):
        mp = self.scene.registry.model_point_for(point)
        if mp is None:
            return None
        junction = self.scene.document.junction_that_contains(mp)
        if junction is None:
            return None
        return self.scene.registry.ui_points_for(junction.points)

    @property
    def groups(self):
        return [self.scene.registry.ui_points_for(j.points)
                for j in self.scene.document.junctions]

    # ------------------------------------------------------------
    #  Linking / unlinking
    # ------------------------------------------------------------
    def link_points(self, a, b):
        self.scene.registry.sync()
        ma = self.scene.registry.model_point_for(a)
        mb = self.scene.registry.model_point_for(b)
        if ma is None or mb is None:
            return
        self.scene.document.link(ma, mb)
        self._sync_linked_flags()
        self.scene.shape_manager.refresh()

    def unlink_point(self, point):
        self.scene.registry.sync()
        mp = self.scene.registry.model_point_for(point)
        if mp is not None:
            self.scene.document.unlink(mp)
        self._sync_linked_flags()
        self.scene.shape_manager.refresh()

    # ------------------------------------------------------------
    #  Propagation (moving linked siblings together)
    # ------------------------------------------------------------
    def propagate_move(self, source, pos):
        if self._propagating:
            return
        self._propagating = True
        try:
            self.scene._propagate_move(source, pos)
        finally:
            self._propagating = False

    # ------------------------------------------------------------
    #  Proximity indicator
    # ------------------------------------------------------------
    def update_proximity(self, point):
        my_group = self.group_of(point)
        nearest = None
        best_d2 = LINK_PROXIMITY_TOLERANCE ** 2
        px, py = point.pos().x(), point.pos().y()

        for curve in self.scene.curves:
            for other in curve.points:
                if other is point:
                    continue
                if my_group is not None and other in my_group:
                    continue
                ox, oy = other.pos().x(), other.pos().y()
                d2 = (ox - px) ** 2 + (oy - py) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    nearest = other

        if nearest is self._proximity_target:
            if nearest is not None:
                self.indicator.show_between(point.pos(), nearest.pos())
            return

        self._proximity_target = nearest
        if nearest is not None:
            self.indicator.show_between(point.pos(), nearest.pos())
        else:
            self.indicator.hide_indicator()

    def clear_proximity(self):
        self._proximity_target = None
        self.indicator.hide_indicator()

    def try_link_proximity(self):
        """Called when the user presses 'L' while dragging a point."""
        if self.scene.dragging_point is None or self._proximity_target is None:
            return False

        source = self.scene.dragging_point
        target = self._proximity_target

        # Clear state *first* so the setPos below doesn't re-show the indicator.
        self.clear_proximity()

        # Link (so they'll move together from now on), then snap.
        self.link_points(source, target)
        source.setPos(target.pos())  # triggers rebuild + on_curve_changed

        scene = self.scene
        scene.messageLogged.emit(
            f"Linked {source.curve.name}·P{source.point_idx} "
            f"→ {target.curve.name}·P{target.point_idx}"
        )
        scene.emit_svg()

        return True

    # ------------------------------------------------------------
    #  Reset
    # ------------------------------------------------------------
    def reset(self):
        self.clear_proximity()
        self.scene.document.junctions.clear()
        self._sync_linked_flags()
        self._propagating = False

    def _sync_linked_flags(self):
        linked_items = set()
        for j in self.scene.document.junctions:
            linked_items.update(self.scene.registry.ui_points_for(j.points))
        for item in self.scene.registry.ui_points():
            item.set_linked(item in linked_items)

    # ------------------------------------------------------------
    #  Break Junction
    # ------------------------------------------------------------
    def try_break_junction(self) -> bool:
        """U key: free every point in the junction the focused (or first
        selected) point belongs to. Returns True if a junction was broken."""
        point = self.scene.focused_point
        if point is None or self.group_of(point) is None:
            point = next((pt for pt in self.scene.selected_points
                          if self.group_of(pt) is not None), None)
        if point is None:
            return False
        return self.break_junction(point)

    def break_junction(self, point) -> bool:
        """Dissolve the junction containing `point` and fan its members out
        along x: +10, -10, +20, -20, … from the junction's position."""
        self.scene.registry.sync()
        mp = self.scene.registry.model_point_for(point)
        if mp is None:
            return False
        junction = self.scene.document.junction_that_contains(mp)
        if junction is None:
            return False

        members = self.scene.registry.ui_points_for(junction.points)
        if len(members) < 2:
            return False

        x, y = point.pos().x(), point.pos().y()

        # Dissolve first, so the setPos calls below propagate to nobody.
        self.scene.document.junctions.remove(junction)
        self._sync_linked_flags()
        self.scene.shape_manager.refresh()

        for i, pt in enumerate(members):
            offset = 10 * (i // 2 + 1)
            sign = 1 if i % 2 == 0 else -1
            pt.setPos(x + sign * offset, y)

        self.scene.messageLogged.emit(
            f"Broke junction — freed {len(members)} point(s)")
        return True