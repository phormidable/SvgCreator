# scene/undo_manager.py
"""UndoManager: linear history of scene snapshots.

Model B (single list of states + position pointer):
  states = [S0, S1, ..., Sn], pos = current position.
  push()    captures the *current* state and appends it.
  undo()    pos -= 1, restore states[pos].
  redo()    pos += 1, restore states[pos].

Each Snapshot holds the document (via save_state) plus the UI state that
belongs with the document: selection. Mode and degree are NOT captured —
they are persistent UI preferences, not document state.

Transient gesture state (live drag, live transform, pending curve) is
never captured, because undo is intercepted before it runs while any of
those is active (see MainWindow._do_undo).
"""

from dataclasses import dataclass, field

from scene.scene_io import save_state, load_state


@dataclass
class Snapshot:
    document: dict
    selection_points: list = field(default_factory=list)   # [(curve_idx, point_idx), ...]
    selection_shapes: list = field(default_factory=list)   # [frozenset(curve_idx), ...]


class UndoManager:
    def __init__(self, scene, limit: int = 50):
        self.scene = scene
        self._limit = limit
        self._states: list[Snapshot] = [self._capture()]
        self._labels: list[str] = []
        self._pos = 0

    # ------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------
    def push(self, label: str):
        """Append the current state under `label`. Truncates any redo tail."""
        del self._states[self._pos + 1:]
        del self._labels[self._pos + 1:]
        self._states.append(self._capture())
        self._labels.append(label)
        self._pos += 1
        if len(self._states) > self._limit + 1:
            self._states.pop(0)
            self._labels.pop(0)
            self._pos -= 1
        self._notify()

    def undo(self) -> str | None:
        if self._pos == 0:
            return None
        self._pos -= 1
        self._restore(self._states[self._pos])
        label = self._labels[self._pos] if self._pos < len(self._labels) else ""
        self._notify()
        return label

    def redo(self) -> str | None:
        if self._pos >= len(self._states) - 1:
            return None
        self._pos += 1
        self._restore(self._states[self._pos])
        label = self._labels[self._pos - 1] if self._pos - 1 < len(self._labels) else ""
        self._notify()
        return label

    def clear(self):
        self._states = [self._capture()]
        self._labels = []
        self._pos = 0
        self._notify()

    # ------------------------------------------------------------
    #  State queries
    # ------------------------------------------------------------
    def can_undo(self) -> bool:
        return self._pos > 0

    def can_redo(self) -> bool:
        return self._pos < len(self._states) - 1

    def undo_label(self) -> str:
        return self._labels[self._pos - 1] if self._pos > 0 else ""

    def redo_label(self) -> str:
        return self._labels[self._pos] if self._pos < len(self._labels) else ""

    def describe(self) -> str:
        return f"{self._pos + 1}/{len(self._states)} (undo={self.can_undo()}, redo={self.can_redo()})"

    # ------------------------------------------------------------
    #  Capture / restore
    # ------------------------------------------------------------
    def _capture(self) -> Snapshot:
        scene = self.scene
        curve_idx = {c: i for i, c in enumerate(scene.curves)}

        pts = []
        for pt in scene.selected_points:
            ci = curve_idx.get(pt.curve)
            if ci is not None:
                pts.append((ci, pt.point_idx))

        shape_sets = []
        for shape in scene.selection.shapes:
            idxs = frozenset(curve_idx[c] for c in scene.ui_curves(shape)
                             if c in curve_idx)
            if idxs:
                shape_sets.append(idxs)

        return Snapshot(
            document=save_state(scene),
            selection_points=pts,
            selection_shapes=shape_sets,
        )

    def _restore(self, snap: Snapshot):
        scene = self.scene

        # 1. Abort any live gesture. load_state() will clear curves;
        #    these fields would otherwise point at soon-dead items.
        scene.mouse.abort_interaction()
        scene.transform.end_transform(commit=False)   # no-op if not transforming
        scene.builder.clear()                          # discard pending curve

        # 2. Reload the document.
        load_state(scene, snap.document, quiet=True)

        # 3. Rebuild selection by index.
        pts = []
        for ci, pi in snap.selection_points:
            try:
                pts.append(scene.curves[ci].points[pi])
            except (IndexError, AttributeError):
                continue
        scene.selection.add_points(pts)

        for curve_set in snap.selection_shapes:
            for shape in scene.shape_manager.shapes:
                if frozenset(scene.ui_curves(shape)) == curve_set:
                    scene.selection.select_shape(shape, add=True)
                    break

    def _notify(self):
        self.scene.undoStateChanged.emit()