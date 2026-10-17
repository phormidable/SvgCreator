# scene/clipboard.py
"""Clipboard: in-memory copy/paste of curves.

The payload is a portable description of the selected curves — degrees,
point positions relative to the selection's bbox centre, internal links,
and coloured shape groups. Paste recreates the curves fresh, centred at
the given point.

Links to points outside the selection are dropped on purpose: pasted
content is self-contained and never reshapes the source.
"""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsItem

from .curve_geometry import curve_bbox
from .items.bezier_curve import BezierCurve


class Clipboard:
    def __init__(self, scene):
        self.scene = scene
        self._payload = None   # None, or the dict built by copy()

    # ------------------------------------------------------------
    #  Copy
    # ------------------------------------------------------------
    def copy(self) -> bool:
        """Serialise every curve touched by the selection. Returns True
        if anything was copied."""
        scene = self.scene

        # Curves touched by the selection, in selection order.
        curves = []
        seen = set()
        for pt in scene.selected_points:
            c = pt.curve
            if c is not None and c not in seen:
                seen.add(c)
                curves.append(c)

        if not curves:
            scene.messageLogged.emit(
                "Nothing to copy — select a curve (A), shape (S) or chain first")
            return False

        # Reference point: bbox centre of the actual curve geometry.
        boxes = []
        for c in curves:
            pts = [(p.model_pos().x(), p.model_pos().y()) for p in c.points]
            boxes.append(curve_bbox(pts, c.degree))
        cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
        cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2

        # Curve payloads, positions relative to the centre.
        curve_payloads = [{
            "degree": c.degree,
            "points": [(p.model_pos().x() - cx, p.model_pos().y() - cy)
                       for p in c.points],
        } for c in curves]

        # Links, kept only when every member lies inside the payload.
        curve_idx = {c: i for i, c in enumerate(curves)}
        links = []
        for junction in scene.document.junctions:
            group = []
            for pt in scene.registry.ui_points_for(junction.points):
                c = pt.curve
                if c in curve_idx:
                    group.append([curve_idx[c], c.points.index(pt)])
            if len(group) >= 2:
                links.append(group)

        # Coloured shapes, kept only when all their curves are inside.
        colors = []
        for shape in scene.shape_manager.shapes:
            if shape.color is None:
                continue
            shape_curves = scene.ui_curves(shape)
            if not all(c in curve_idx for c in shape_curves):
                continue
            colors.append({
                "curves": [curve_idx[c] for c in shape_curves],
                "color": shape.color.name(),
            })

        self._payload = {"curves": curve_payloads, "links": links, "colors": colors}
        scene.messageLogged.emit(f"Copied {len(curves)} curve(s)")
        return True

    # ------------------------------------------------------------
    #  Paste
    # ------------------------------------------------------------
    def paste(self, center: QPointF) -> int:
        """Recreate the clipboard content at `center`. Returns the number
        of curves created (0 on empty clipboard)."""
        scene = self.scene
        if self._payload is None:
            scene.messageLogged.emit("Clipboard is empty — copy something first")
            return 0

        # ---- 1. Build new curves. ----
        new_curves = []
        for cp in self._payload["curves"]:
            c = BezierCurve(scene, degree=cp["degree"])
            for dx, dy in cp["points"]:
                c.add_point(QPointF(center.x() + dx, center.y() + dy))
            c.committed = True
            for pt in c.points:
                pt.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            scene.curves.append(c)
            new_curves.append(c)

        # ---- 2. Restore internal links. ----
        for group in self._payload["links"]:
            pts = [new_curves[ci].points[pi] for ci, pi in group]
            for i in range(len(pts) - 1):
                scene.link_manager.link_points(pts[i], pts[i + 1])

        # ---- 3. Apply shape colours. ----
        scene.shape_manager.refresh()
        for entry in self._payload["colors"]:
            target = frozenset(new_curves[i] for i in entry["curves"])
            for shape in scene.shape_manager.shapes:
                if frozenset(scene.ui_curves(shape)) == target:
                    scene.shape_manager.set_color(shape, QColor(entry["color"]))
                    break

        # ---- 4. Select what we just pasted. ----
        scene.clear_selection()
        scene.selection.add_points([pt for c in new_curves for pt in c.points])

        scene.emit_svg()
        scene.messageLogged.emit(f"Pasted {len(new_curves)} curve(s)")
        return len(new_curves)