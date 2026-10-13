# model_registry.py
"""ModelRegistry: the UI ↔ model bridge.

Owns the four maps between Qt items (ControlPoint, BezierCurve) and the
Qt-free model (Point, Curve), plus the sync routine that keeps them
current with scene.curves.
"""

from core.model import Point, Curve


class ModelRegistry:
    def __init__(self, scene):
        self.scene = scene
        self._curve_by_model = {}
        self._model_by_curve = {}
        self._pt_by_model = {}
        self._model_by_pt = {}

    # ------------------------------------------------------------
    #  Lookups
    # ------------------------------------------------------------
    def model_point_for(self, ui_pt):
        return self._model_by_pt.get(ui_pt)

    def ui_points_for(self, model_pts):
        """Translate a list of model points to UI points, dropping any
        that aren't registered."""
        d = self._pt_by_model
        return [d[mp] for mp in model_pts if mp in d]

    def ui_points(self):
        return list(self._pt_by_model.values())

    def model_curve_for(self, ui_curve):
        return self._model_by_curve.get(ui_curve)

    def ui_curve_for(self, model_curve):
        return self._curve_by_model.get(model_curve)

    def ui_curves(self, shape):
        """The UI BezierCurve objects for a model Shape."""
        d = self._curve_by_model
        return [d[mc] for mc in shape.curves if mc in d]


    # ------------------------------------------------------------
    #  Sync
    # ------------------------------------------------------------
    def sync(self):
        """Sync the model with the scene's current items. Additive: model
        Curve/Point objects persist across calls so identity is stable."""
        doc = self.scene.document
        current = set(self.scene.curves)

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
        for curve_item in self.scene.curves:
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