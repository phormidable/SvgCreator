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
from shape import Shape as UIShape
from new_data_model import Document, Point, Junction, Curve


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

        # 4. Deselect any selected shape that dissolved.
        for shape in list(self._selected_shapes):
            if shape not in new_shapes:
                self.deselect(shape)
                self.scene.messageLogged.emit(f"{shape.name} dissolved")

        self.shapes = new_shapes
        self._ui_by_model_id = new_by_id

        self._apply_transparency_to_all()
        self.update_fills()

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


class BezierSceneV2(BezierScene):
    def __init__(self):
        super().__init__()
        self.document = Document()
        self._curve_by_model: dict[Curve, "BezierCurve"] = {}
        # Replace the base ShapeManager with the model-routed one.
        self.shape_manager = ShapeManagerV2(self)

    def _mirror_to_document(self):
        """Rebuild the model's lists from the scene's current items.
        Temporary bridge — goes away when the model becomes authoritative."""
        doc = self.document
        doc.extremities.clear()
        doc.controls.clear()
        doc.curves.clear()
        doc.junctions.clear()

        pt_map: dict = {}
        self._curve_by_model.clear()

        for curve_item in self.curves:
            if not curve_item.is_complete():
                continue
            pts = curve_item.points
            mps = []
            for pt_item in pts:
                mp = Point(pt_item.pos().x(), pt_item.pos().y())
                pt_map[pt_item] = mp
                mps.append(mp)

            extremities = (mps[0], mps[-1])
            controls = mps[1:-1]
            mc = Curve(extremities, controls, curve_item.degree)
            # Align IDs with the UI curve IDs so shape identity survives
            # across mirrors (the model matches shapes by curve-ID set).
            mc.id = curve_item.id
            doc.curves.append(mc)
            self._curve_by_model[mc] = curve_item

            doc.extremities.extend(extremities)
            doc.controls.extend(controls)

        for group in self.link_manager.groups:
            jpoints = [pt_map[g] for g in group if g in pt_map]
            if len(jpoints) >= 2:
                doc.junctions.append(Junction(jpoints))