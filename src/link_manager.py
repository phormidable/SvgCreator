# link_manager.py
"""LinkManager: owns the link groups that snap control points together,
plus the flashing proximity indicator shown while dragging a point near
a potential link target.

A link group is a list of ControlPoint that stay coincident and move as
one. Groups with fewer than 2 members are dissolved.

Owned state: groups, _propagating, _proximity_target, indicator.
"""

from settings import LINK_PROXIMITY_TOLERANCE
from link_indicator import LinkIndicator


class LinkManager:
    def __init__(self, scene):
        self.scene = scene
        self.groups: list[list] = []
        self._propagating = False
        self._proximity_target = None
        self.indicator = LinkIndicator()
        scene.addItem(self.indicator)

    # ------------------------------------------------------------
    #  Group lookup
    # ------------------------------------------------------------
    def group_of(self, point):
        """Return the link group containing `point`, or None."""
        for group in self.groups:
            for pt in group:
                if pt is point:
                    return group
        return None

    # ------------------------------------------------------------
    #  Linking / unlinking
    # ------------------------------------------------------------
    def link_points(self, a, b):
        """Merge a's and b's link groups (creating one if needed)."""
        ga = self.group_of(a)
        gb = self.group_of(b)

        if ga is not None and ga is gb:
            return  # already linked

        if ga is None and gb is None:
            group = [a, b]
            self.groups.append(group)
        elif ga is None:
            gb.append(a)
            group = gb
        elif gb is None:
            ga.append(b)
            group = ga
        else:
            ga.extend(gb)
            self.groups.remove(gb)
            group = ga

        for pt in group:
            pt.set_linked(True)

        self.scene.shape_manager.refresh()

    def unlink_point(self, point):
        """Remove `point` from its group. Dissolve the group if <2 remain."""
        for gi, group in enumerate(self.groups):
            for pi, pt in enumerate(group):
                if pt is point:
                    del group[pi]
                    if len(group) < 2:
                        for remaining in group:
                            remaining.set_linked(False)
                        del self.groups[gi]
                    self.scene.shape_manager.refresh()
                    return

    # ------------------------------------------------------------
    #  Propagation (moving linked siblings together)
    # ------------------------------------------------------------
    def propagate_move(self, source, pos):
        """Move every other point in source's group to `pos`."""
        if self._propagating:
            return
        group = self.group_of(source)
        if group is None:
            return
        self._propagating = True
        try:
            for pt in group:
                if pt is not source:
                    pt.setPos(pos)
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
        scene.pointsChanged.emit()
        return True

    # ------------------------------------------------------------
    #  Reset
    # ------------------------------------------------------------
    def reset(self):
        """Drop every group and hide the indicator (used by clear_all)."""
        self.clear_proximity()
        self.groups.clear()
        self._propagating = False