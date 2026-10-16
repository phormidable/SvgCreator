# ui/preset_panel.py
from PySide6.QtWidgets import QGroupBox, QGridLayout, QToolButton
from PySide6.QtCore import Signal

from core.presets import PRESETS
from core.settings import PRESET_PANEL_HEIGHT

class PresetPanel(QGroupBox):
    """Grid of preset buttons. Clicking one arms it in the scene; the next
    canvas click places it. Clicking the armed button again cancels."""

    presetRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Presets", parent)
        self._buttons: dict[str, QToolButton] = {}

        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(4, 2, 4, 2)
        self.setFixedHeight(PRESET_PANEL_HEIGHT)
        cols = 10
        for i, preset in enumerate(PRESETS.values()):
            btn = QToolButton()
            btn.setText(preset.label)
            btn.setCheckable(True)
            btn.setToolTip(preset.tooltip)
            btn.setMinimumSize(34, 26)
            btn.clicked.connect(
                lambda _checked, n=preset.name: self.presetRequested.emit(n))
            grid.addWidget(btn, i // cols, i % cols)
            self._buttons[preset.name] = btn

        self.setLayout(grid)

    def sync_state(self, armed: str):
        """Check the button matching `armed` and uncheck the others.
        Empty string means nothing is armed."""
        for name, btn in self._buttons.items():
            btn.setChecked(name == armed)