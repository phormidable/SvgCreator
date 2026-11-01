class ModelRegistry:
    """Explicit, 1-to-1 mapping between UI QGraphicsItems and pure Python Model objects."""

    def __init__(self, scene):
        self.scene = scene
        self._model_by_curve = {}  # UI Curve -> Model Curve
        self._curve_by_model = {}  # Model Curve -> UI Curve
        self._pt_by_model = {}  # Model Point -> UI Point
        self._model_by_pt = {}  # UI Point -> Model Point

    # ------------------------------------------------------------
    #  Binding (called once at creation time)
    # ------------------------------------------------------------
    def bind(self, ui_curve, model_curve):
        self._model_by_curve[ui_curve] = model_curve
        self._curve_by_model[model_curve] = ui_curve

    def bind_point(self, ui_point, model_point):
        self._model_by_pt[ui_point] = model_point
        self._pt_by_model[model_point] = ui_point

    # ------------------------------------------------------------
    #  Lookups (with backward compatibility)
    # ------------------------------------------------------------
    def model_curve_for(self, ui_curve):
        return self._model_by_curve.get(ui_curve)

    def ui_curve_for(self, model_curve):
        return self._curve_by_model.get(model_curve)

    def model_point_for(self, ui_point):
        return self._model_by_pt.get(ui_point)

    def ui_point_for(self, model_point):
        return self._pt_by_model.get(model_point)

    def ui_curves(self, shape):
        """Helper to get UI curves for a model shape."""
        return [self.ui_curve_for(mc) for mc in shape.curves
                if self.ui_curve_for(mc) is not None]

    def ui_points(self, model_points=None):
        """Get UI points. If model_points is None, return ALL UI points.
        If model_points is provided, return UI points for those specific model points."""
        if model_points is None:
            # Return all UI points (values, not keys!)
            return list(self._pt_by_model.values())
        else:
            # Return UI points for specific model points
            return [self.ui_point_for(mp) for mp in model_points
                    if self.ui_point_for(mp) is not None]

    def ui_points_for(self, model_points):
        """Get UI points for a collection of model points."""
        return [self.ui_point_for(mp) for mp in model_points
                if self.ui_point_for(mp) is not None]

    def model_points(self, ui_points=None):
        """Get model points. If ui_points is None, return ALL model points.
        If ui_points is provided, return model points for those specific UI points."""
        if ui_points is None:
            # Return all model points
            return list(self._model_by_pt.keys())
        else:
            # Return model points for specific UI points
            return [self.model_point_for(up) for up in ui_points
                    if self.model_point_for(up) is not None]

    def reset(self):
        """Drop all mappings. Used when clearing the scene."""
        self._model_by_curve.clear()
        self._curve_by_model.clear()
        self._pt_by_model.clear()
        self._model_by_pt.clear()