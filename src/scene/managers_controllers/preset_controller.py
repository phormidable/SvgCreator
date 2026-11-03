# scene/managers_controllers/preset_controller.py
from PySide6.QtCore import QPointF

from core.presets import PRESETS


class PresetController:
    """Arm a preset from the panel; the next canvas click places it."""

    def __init__(self, scene):
        self.scene = scene
        self._pending: str | None = None

    @property
    def pending(self) -> str | None:
        return self._pending

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
        if self.scene.builder.pending_curve is not None:
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
    def place_preset(self, center: QPointF, keep_armed: bool = False):
        name = self._pending
        if not keep_armed:
            self._pending = None
            self.scene.presetStateChanged.emit("")

        preset = PRESETS[name]
        degree = self.scene.builder.current_degree
        curves = []
        for cdef in preset.curves:
            d, offsets = cdef.for_degree(degree)
            cwidth = self.scene.stroke_start_width
            curve = self.scene.builder.build_from_offsets(center, offsets, d, start_width=cwidth, end_width=cwidth)
            curves.append(curve)

        for (ci, pi), (cj, pj) in preset.links:
            self.scene.link_manager.link_points(
                curves[ci].points[pi], curves[cj].points[pj])

        degrees = {c.degree for c in curves}
        kind = "mixed" if len(degrees) > 1 else ("cubic" if 3 in degrees else "quadratic")
        if keep_armed:
            self.scene.messageLogged.emit(
                f"{preset.label} placed ({kind}) — still armed, release Shift to stop")
        else:
            self.scene.messageLogged.emit(f"{preset.label} placed ({kind})")

        self.scene.undo.push(f"Place {preset.label}")