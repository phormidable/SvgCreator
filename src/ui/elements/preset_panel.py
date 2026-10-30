# ui/elements/preset_panel.py
from PySide6.QtWidgets import (QButtonGroup, QGridLayout, QGroupBox, QHBoxLayout, QToolButton, QVBoxLayout)
from PySide6.QtCore import Signal

from core.presets import PRESETS
from core.settings import PRESET_PANEL_HEIGHT, TOOLBAR_CHECKED_STYLE


class PresetPanel(QGroupBox):
    """Category row on top, preset grid below. Clicking a preset arms it in
    the scene; the next canvas click places it. Clicking the armed button
    again cancels. Switching category hides the non-matching buttons but
    leaves any armed preset untouched on the scene side."""

    presetRequested = Signal(str)

    CATEGORIES = ["Polygons", "Curves", "Chains", "Shapes", "Letters"]
    COLUMNS = 10

    def __init__(self, parent=None):
        super().__init__("Presets", parent)
        self._preset_buttons: dict[str, QToolButton] = {}
        self._category_buttons: dict[str, QToolButton] = {}
        self._current_category: str | None = None

        self.setFixedHeight(PRESET_PANEL_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setSpacing(2)
        outer.setContentsMargins(4, 2, 4, 2)

        # ---- Category row ----
        cat_row = QHBoxLayout()
        cat_row.setSpacing(2)
        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)

        for cat in self.CATEGORIES:
            btn = QToolButton()
            btn.setText(cat)
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setStyleSheet(TOOLBAR_CHECKED_STYLE)
            btn.clicked.connect(lambda _c, c=cat: self._show_category(c))
            self._category_group.addButton(btn)
            self._category_buttons[cat] = btn
            cat_row.addWidget(btn)
        cat_row.addStretch()
        outer.addLayout(cat_row)

        # ---- Grid area (repopulated by _show_category) ----
        self._grid = QGridLayout()
        self._grid.setSpacing(2)
        self._grid.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._grid)
        outer.addStretch()

        # ---- Build every preset button once, hidden ----
        for preset in PRESETS.values():
            btn = QToolButton()
            btn.setText(preset.label)
            btn.setCheckable(True)
            btn.setToolTip(preset.tooltip)
            btn.setMinimumSize(30, 22)
            btn.clicked.connect(
                lambda _checked, n=preset.name: self.presetRequested.emit(n))
            btn.hide()
            self._preset_buttons[preset.name] = btn

        # ---- Show the first category ----
        first = self.CATEGORIES[0]
        self._category_buttons[first].setChecked(True)
        self._show_category(first)

    # ------------------------------------------------------------
    #  Category switching
    # ------------------------------------------------------------
    def _show_category(self, category: str):
        if category == self._current_category:
            return

        # Take every button out of the grid (they stay alive, just hidden).
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()

        # Add the ones belonging to this category.
        i = 0
        for preset in PRESETS.values():
            if preset.category != category:
                continue
            btn = self._preset_buttons[preset.name]
            self._grid.addWidget(btn, i // self.COLUMNS, i % self.COLUMNS)
            btn.show()
            i += 1

        self._current_category = category

    # ------------------------------------------------------------
    #  Armed-state sync (called by the scene)
    # ------------------------------------------------------------
    def sync_state(self, armed: str):
        """Check the button matching `armed` and uncheck the others.
        Empty string means nothing is armed. Works across categories:
        buttons that are currently hidden just update their checked state."""
        for name, btn in self._preset_buttons.items():
            btn.setChecked(name == armed)