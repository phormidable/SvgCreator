# preset_controller.py
from PySide6.QtCore import QPointF

from presets import PRESETS
from bezier_curve import BezierCurve


class PresetController:
    """Arm a preset from the panel; the next canvas click places it."""

    def __init__(self, scene):
        self.scene = scene
        self._pending: str | None = None

    # ------------------------------------------------------------
    #  Arm / cancel
    # ------------------------------------------------------------
    def arm_preset(self, name: str) -> bool:
        if name not in PRESETS:
            return False
        if self._pending == name:
            self._pending = None
            self.scene.presetStateChanged.emit("")
            self.scene.messageLogged.emit("Preset cancelled")
            return True
        if self.scene.pending_curve is not None:
            # Refused: sync the panel back to whatever state we're actually in.
            self.scene.presetStateChanged.emit(self._pending or "")
            self.scene.messageLogged.emit("Finish or discard the current curve first")
            return False
        self._pending = name
        self.scene.presetStateChanged.emit(name)
        self.scene.messageLogged.emit(
            f"Click the canvas to place '{PRESETS[name].label}'")
        return True

    def cancel_preset(self) -> bool:
        if self._pending is None:
            return False
        self._pending = None
        self.scene.presetStateChanged.emit("")
        self.scene.messageLogged.emit("Preset cancelled")
        return True

    def on_shift_released(self):
        """Releasing shift after shift-click placement unarms the preset."""
        if self._pending is not None:
            self.cancel_preset()

    # ------------------------------------------------------------
    #  Placement
    # ------------------------------------------------------------
    def _place_preset(self, center: QPointF, keep_armed: bool = False):
        name = self._pending
        if not keep_armed:
            self._pending = None
            self.scene.presetStateChanged.emit("")

        preset = PRESETS[name]
        degree = self.scene.current_degree
        curves = []
        for cdef in preset.curves:
            curve = BezierCurve(self.scene, degree=degree)
            for dx, dy in cdef.offsets_for_degree(degree):
                curve.add_point(QPointF(center.x() + dx, center.y() + dy))
            self.scene.pending_curve = curve
            self.scene.finalize_curve()
            curves.append(curve)

        for (ci, pi), (cj, pj) in preset.links:
            self.scene.link_manager.link_points(
                curves[ci].points[pi], curves[cj].points[pj])

        kind = "cubic" if degree == 3 else "quadratic"
        if keep_armed:
            self.scene.messageLogged.emit(
                f"{preset.label} placed ({kind}) — still armed, release Shift to stop")
        else:
            self.scene.messageLogged.emit(f"{preset.label} placed ({kind})")