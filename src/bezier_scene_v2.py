# bezier_scene_v2.py
"""BezierSceneV2: temporary testbed for the new data model.

Behaves exactly like BezierScene, except shape detection goes through
model.Document. Everything else — items, event handling, transforms,
presets, save/load — is inherited unchanged.

Once the pattern is proven, this gets inlined back into bezier_scene.py
and the base class goes away.
"""

from bezier_scene import BezierScene
from shape_manager import ShapeManager
from link_manager import LinkManager
from shape import Shape as UIShape
from new_data_model import Document, Point, Junction, Curve
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem
from control_point import ControlPoint
from bezier_curve import BezierCurve

def _add_point_v2(self, pos):
    pt = ControlPointV2(pos, self, len(self.points))
    self._scene.addItem(pt)
    self.points.append(pt)
    if self.committed:
        pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    self.rebuild_path()
    return pt

BezierCurve.add_point = _add_point_v2

class ControlPointV2(ControlPoint):
    """ControlPoint whose position lives in the model once mapped.

    - pos() reads from the model (falls back to Qt's internal position
      before the point has been mirrored, and after it's been removed).
    - itemChange(ItemPositionHasChanged) writes the clamped Qt position
      into the model BEFORE the base class runs propagation, so any
      pos() read inside propagate_move/on_point_moved sees the new value.
    """

    def pos(self):
        scene = self.curve.scene() if self.curve is not None else None
        if scene is not None:
            mp = scene._model_by_pt.get(self)
            if mp is not None:
                return QPointF(mp.x, mp.y)
        return super().pos()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.curve.scene() if self.curve is not None else None
            if scene is not None:
                mp = scene._model_by_pt.get(self)
                if mp is not None:
                    p = super().pos()   # Qt's internal = post-clamp value
                    mp.x = p.x()
                    mp.y = p.y()
        return super().itemChange(change, value)

class ShapeManagerV2(ShapeManager):
    """Routes shape detection through the model, but keeps the UI Shape
    objects (colour, fill_item, name) across refresh calls by keying on
    the model's stable shape IDs."""

    def __init__(self, scene):
        super().__init__(scene)
        self._ui_by_model_id: dict[int, UIShape] = {}

    def refresh(self):
        # 1. Sync the model from the scene's current items.
        self.scene._mirror_to_document()

        # 2. Ask the model to detect shapes.
        self.scene.document.detect_shapes()
        self.scene.document.detect_chains()

        # 3. Translate model shapes → UI shapes, preserving identity.
        new_shapes = []
        new_by_id = {}
        for mshape in self.scene.document.shapes:
            ui_shape = self._ui_by_model_id.get(mshape.id)
            ui_curves = frozenset(
                self.scene._curve_by_model[mc] for mc in mshape.curves
            )
            if ui_shape is None:
                ui_shape = UIShape(ui_curves)
                ui_shape.name = mshape.name
                names = " + ".join(
                    c.name for c in sorted(ui_curves, key=lambda c: c.id))
                self.scene.messageLogged.emit(
                    f"{ui_shape.name} formed from {names}")
            new_shapes.append(ui_shape)
            new_by_id[mshape.id] = ui_shape

        # 4. Clean up any UI shape that dissolved: remove its fill, revert
        # its curves to the scene's default colour, and drop its selection.
        curves_in_new_shapes = set()
        for s in new_shapes:
            curves_in_new_shapes.update(s.curves)

        for shape in list(self.shapes):
            if shape in new_shapes:
                continue
            if shape.fill_item is not None:
                self.scene.removeItem(shape.fill_item)
                shape.fill_item = None
            if shape.color is not None:
                for curve in shape.curves:
                    if curve not in curves_in_new_shapes:
                        curve.set_color(self.scene.curve_color)
                shape.color = None
            if shape in self._selected_shapes:
                self.deselect(shape)
            self.scene.messageLogged.emit(f"{shape.name} dissolved")

        self.shapes = new_shapes
        self._ui_by_model_id = new_by_id

        self._apply_transparency_to_all()
        self.update_fills()

    def _propagate_move(self, source, pos):
        """Junction lookup via the model, then push the position to siblings."""
        mp = self._model_by_pt.get(source)
        if mp is None:
            return
        junction = self.document.junction_that_contains(mp)
        if junction is None:
            return
        for mpt in junction.points:
            if mpt is mp:
                continue
            item = self._pt_by_model.get(mpt)
            if item is not None:
                item.setPos(pos)

    def reset(self):
        super().reset()
        self._ui_by_model_id.clear()
        doc = self.scene.document
        doc.extremities.clear()
        doc.controls.clear()
        doc.curves.clear()
        doc.junctions.clear()
        doc.shapes.clear()
        doc.chains.clear()

    def rebuild_from_links(self):
        self._ui_by_model_id.clear()
        super().rebuild_from_links()

    def chain_of(self, curve):
        """The chain containing `curve`, as UI curves. Reads from the model
        (populated by refresh) rather than walking link groups directly."""
        mcurve = self.scene._model_by_curve.get(curve)
        if mcurve is None:
            return [curve]
        for mchain in self.scene.document.chains:
            if mcurve in mchain.curves:
                return [self.scene._curve_by_model[mc]
                        for mc in mchain.curves
                        if mc in self.scene._curve_by_model]
        return [curve]

    # ------------------------------------------------------------
    #  Loop ordering — junction-tolerant
    # ------------------------------------------------------------
    def _ordered_loop(self, shape):
        """Return [(curve, enter_i), ...] in cyclic order, or None.
        `enter_i` is the index (0 or 1) of the curve's endpoint we enter at."""
        curves = list(shape.curves)
        if not curves:
            return None
        if len(curves) == 1:
            return [(curves[0], 0)]

        def neighbor(c, exit_i):
            end = c.points[0] if exit_i == 0 else c.points[-1]
            g = self.scene.link_manager.group_of(end)
            if g is None:
                return None
            options = []
            for other in curves:
                if other is c:
                    continue
                for i, oe in ((0, other.points[0]), (1, other.points[-1])):
                    if oe in g:
                        options.append((other, i))
                        break
            if len(options) != 1:
                return None      # branching shape → not a simple cycle
            return options[0]

        start = curves[0]
        order = [(start, 0)]
        visited = {start}
        cur, enter_i = start, 0
        while True:
            exit_i = 1 - enter_i
            n = neighbor(cur, exit_i)
            if n is None:
                return None
            nxt, arrive_i = n
            if nxt is start:
                break
            if nxt in visited:
                return None
            order.append((nxt, arrive_i))
            visited.add(nxt)
            cur, enter_i = nxt, arrive_i
        if len(order) != len(curves):
            return None
        return order

    def _loop_segments(self, shape):
        order = self._ordered_loop(shape)
        if order is None:
            return None
        if len(order) == 1:
            c, _ = order[0]
            start_pt = c.points[0]
            c1, c2, end_pt = c.cubic_segment(start_pt)
            return start_pt.pos(), [(c1, c2, end_pt.pos())]

        first_curve, first_enter = order[0]
        start_pt = first_curve.points[first_enter]
        segments = []
        for curve, enter_i in order:
            pt = curve.points[enter_i]
            c1, c2, other = curve.cubic_segment(pt)
            segments.append((c1, c2, other.pos()))
        return start_pt.pos(), segments



class LinkManagerV2(LinkManager):
    def group_of(self, point):
        """Read from the model instead of the local groups list."""
        mp = self.scene._model_by_pt.get(point)
        if mp is None:
            return None
        junction = self.scene.document.junction_that_contains(mp)
        if junction is None:
            return None
        return [self.scene._pt_by_model[m] for m in junction.points
                if m in self.scene._pt_by_model]

    @property
    def groups(self):
        """Read-only view: link groups as lists of UI points."""
        return [
            [self.scene._pt_by_model[m] for m in j.points
             if m in self.scene._pt_by_model]
            for j in self.scene.document.junctions
        ]

    def link_points(self, a, b):
        self.scene._mirror_to_document()
        ma = self.scene._model_by_pt.get(a)
        mb = self.scene._model_by_pt.get(b)
        if ma is None or mb is None:
            return
        self.scene.document.link(ma, mb)
        self._sync_linked_flags()
        self.scene.shape_manager.refresh()

    def unlink_point(self, point):
        self.scene._mirror_to_document()
        mp = self.scene._model_by_pt.get(point)
        if mp is not None:
            self.scene.document.unlink(mp)
        self._sync_linked_flags()
        self.scene.shape_manager.refresh()

    def reset(self):
        self.clear_proximity()
        self.scene.document.junctions.clear()
        self._sync_linked_flags()
        self._propagating = False

    def _sync_linked_flags(self):
        """Set `linked` on every UI point that's in a junction, clear it
        on every other UI point."""
        linked_items = set()
        for j in self.scene.document.junctions:
            for m in j.points:
                item = self.scene._pt_by_model.get(m)
                if item is not None:
                    linked_items.add(item)
        for item in self.scene._model_by_pt:
            item.set_linked(item in linked_items)




class BezierSceneV2(BezierScene):
    def __init__(self):
        super().__init__()
        self.document = Document()
        self._curve_by_model: dict[Curve, "BezierCurve"] = {}
        self._model_by_curve: dict["BezierCurve", Curve] = {}
        self._pt_by_model: dict[Point, "ControlPoint"] = {}
        self._model_by_pt: dict["ControlPoint", Point] = {}
        self.shape_manager = ShapeManagerV2(self)
        self.link_manager = LinkManagerV2(self)

    def on_shift_released(self):
        """Releasing shift after shift-click placement unarms the preset."""
        if self._preset_pending is not None:
            self.cancel_preset()

    def _mirror_to_document(self):
        """Sync the model with the scene's current items. Additive: model
        Curve/Point objects persist across calls so identity is stable."""
        doc = self.document
        current = set(self.curves)

        # --- 1. Remove model curves whose UI items are gone. ---
        for curve_item in list(self._model_by_curve):
            if curve_item in current:
                continue
            mc = self._model_by_curve.pop(curve_item)
            self._curve_by_model.pop(mc, None)
            for mp in (*mc.extremities, *mc.controls):
                j = doc.junction_that_contains(mp)
                if j is not None:
                    doc.unlink(mp)
                item = self._pt_by_model.pop(mp, None)
                if item is not None:
                    self._model_by_pt.pop(item, None)
                if mp in doc.extremities:
                    doc.extremities.remove(mp)
                elif mp in doc.controls:
                    doc.controls.remove(mp)
            if mc in doc.curves:
                doc.curves.remove(mc)

        # --- 2. Add new curves / refresh positions on existing ones. ---
        for curve_item in self.curves:
            if not curve_item.is_complete():
                continue
            ui_pts = curve_item.points
            mc = self._model_by_curve.get(curve_item)
            if mc is None:
                mps = []
                for pt_item in ui_pts:
                    mp = Point(pt_item.pos().x(), pt_item.pos().y())
                    mps.append(mp)
                    self._pt_by_model[mp] = pt_item
                    self._model_by_pt[pt_item] = mp
                extremities = (mps[0], mps[-1])
                controls = mps[1:-1]
                mc = Curve(extremities, controls, curve_item.degree)
                mc.id = curve_item.id
                doc.curves.append(mc)
                doc.extremities.extend(extremities)
                doc.controls.extend(controls)
                self._model_by_curve[curve_item] = mc
                self._curve_by_model[mc] = curve_item
            # else:
            #     for mp, pt_item in zip(
            #             (*mc.extremities, *mc.controls), ui_pts):
            #         mp.x = pt_item.pos().x()
            #         mp.y = pt_item.pos().y()
