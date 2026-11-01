# ui/elements/main_toolbar.py
"""MainToolBar: construction and widget-level behaviour of the main toolbar.

Split of responsibilities:
- the window owns the *actions* (what happens when you click),
- the toolbar owns the *widgets* (how they look, what they display, and
  keeping them in sync with the scene).

Anything that only reads/writes a combo box lives here. Anything that
touches the scene's mode or the document stays in MainWindow.
"""

from PySide6.QtWidgets import (QToolBar, QLabel, QComboBox, QToolButton, QMenu,
                               QWidget, QSizePolicy)

from core.settings import (ZOOM_LEVELS, GRID_SIZE_OPTIONS, GRID_DEFAULT_SPACING,
                           TOOLBAR_CHECKED_STYLE)

MODE_ITEMS = [("Create", "create"), ("Edit", "edit")]

TYPE_ITEMS = [
    ("Line",             (1, False)),
    ("Line Stroke",      (1, True)),
    ("Quadratic",        (2, False)),
    ("Quadratic Stroke", (2, True)),
    ("Cubic",            (3, False)),
    ("Cubic Stroke",     (3, True)),
]


class MainToolBar(QToolBar):
    def __init__(self, window):
        super().__init__("Tools", window)
        self.window = window
        self.scene = window.scene
        window.addToolBar(self)

        self._build_history()
        self.addSeparator()
        self._build_mode()
        self.addSeparator()
        self._build_type()
        self.addSeparator()
        self._build_zoom()
        self.addSeparator()
        self._build_grid()
        self.addSeparator()
        self._build_files_menu()

        act = self.addAction("💾💾→")
        act.setToolTip("Save and Export to configured folders")
        act.triggered.connect(self.window.save_and_export_to_folders)

        self._build_effects_menu()
        self._build_settings()
        self._build_right_group()

    # ------------------------------------------------------------
    #  Small construction helpers
    # ------------------------------------------------------------
    def _combo(self, items, slot, initial: int = 0) -> QComboBox:
        """Add a combo populated with (label, data) pairs. The initial index
        is set *before* connecting, so startup doesn't fire the slot."""
        combo = QComboBox()
        for label, data in items:
            combo.addItem(label, data)
        combo.setCurrentIndex(initial)
        combo.currentIndexChanged.connect(slot)
        self.addWidget(combo)
        return combo

    @staticmethod
    def _action(menu, text, tip, slot, shortcut=None):
        act = menu.addAction(text)
        if tip:
            act.setToolTip(tip)
        if shortcut:
            act.setShortcut(shortcut)
        act.triggered.connect(slot)
        return act

    def _add_menu_button(self, title: str, menu: QMenu):
        btn = QToolButton()
        btn.setText(title)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setMenu(menu)
        self.addWidget(btn)

    def _mark_checkable(self, action):
        """Red background when checked (widgetForAction gives the QToolButton)."""
        btn = self.widgetForAction(action)
        if btn is not None:
            btn.setStyleSheet(TOOLBAR_CHECKED_STYLE)

    # ------------------------------------------------------------
    #  Sections
    # ------------------------------------------------------------
    def _build_history(self):
        self.undo_action = self.addAction("↶")
        self.undo_action.setToolTip("Undo (Ctrl+Z)")
        self.undo_action.setEnabled(False)
        self.undo_action.triggered.connect(self.window._do_undo)

        self.redo_action = self.addAction("↷")
        self.redo_action.setToolTip("Redo (Ctrl+Shift+Z / Ctrl+Y)")
        self.redo_action.setEnabled(False)
        self.redo_action.triggered.connect(self.window._do_redo)

    def _build_mode(self):
        self.addWidget(QLabel(" Mode: "))
        self.mode_combo = self._combo(MODE_ITEMS, self._on_mode_changed)

    def _build_type(self):
        self.addWidget(QLabel(" Type: "))
        builder = self.scene.builder
        wanted = (builder.current_degree, builder.current_stroke_width is not None)
        initial = next((i for i, (_, style) in enumerate(TYPE_ITEMS)
                        if style == wanted), 0)
        self.degree_combo = self._combo(TYPE_ITEMS, self._on_degree_changed, initial)

    def _build_zoom(self):
        self.addWidget(QLabel(" Zoom: "))
        self.zoom_combo = self._combo(ZOOM_LEVELS, self._on_zoom_changed, initial=1)

    def _build_grid(self):
        self.grid_action = self.addAction("Show Grid")
        self.grid_action.setCheckable(True)
        self.grid_action.toggled.connect(self._on_grid_toggled)
        self._mark_checkable(self.grid_action)

        self.addWidget(QLabel(" Grid size: "))
        initial = next((i for i, (_, s) in enumerate(GRID_SIZE_OPTIONS)
                        if s == GRID_DEFAULT_SPACING), 0)
        self.grid_combo = self._combo(GRID_SIZE_OPTIONS, self._on_grid_size_changed, initial)

        # Start with the grid shown. Fires toggled(True) — must stay *after*
        # the connect above.
        self.grid_action.setChecked(True)

        self.snap_action = self.addAction("Snap to Grid")
        self.snap_action.setCheckable(True)
        self.snap_action.toggled.connect(self.scene.set_snap_enabled)
        self._mark_checkable(self.snap_action)

    def _build_files_menu(self):
        w = self.window
        menu = QMenu(self)
        self._action(menu, "📂 Load", None, w.file_io.load_project, "Ctrl+O")
        self._action(menu, "💾 Save", None, w.file_io.save_project, "Ctrl+S")
        self._action(menu, "💾 Export SVG", None, w.file_io.export_svg)
        self._action(menu, "💾💾 Save and Export","Save both JSON and SVG with the same filename",w.save_and_export_dialog)
        self._action(menu, "📐 Save Shape","Save the selected shape, chain, or curve as a reusable preset",w.save_selected_shape)
        self._add_menu_button("📁 Files", menu)

    def _build_effects_menu(self):
        w, scene = self.window, self.scene
        menu = QMenu(self)
        self._action(menu, "🪞 Mirror X","Flip vertically — mirror across the horizontal line through the selection", lambda: scene.mirror_selection("x"))
        self._action(menu, "🪞 Mirror Y","Flip horizontally — mirror across the vertical line through the selection", lambda: scene.mirror_selection("y"))
        self._action(menu, "↔ Center H","Centre the selection horizontally in the viewbox", lambda: scene.center_selection("horizontal"))
        self._action(menu, "↕ Center V","Centre the selection vertically in the viewbox", lambda: scene.center_selection("vertical"))

        menu.addSeparator()

        self._action(menu, "📏 Create Line","Connect the two selected points with a line (J)",
                     lambda: scene.selection_ops.join_with_line(link=False))
        self._action(menu, "📏🔗 Create Line and Join","Connect and link the two selected points (Ctrl+J)",
                     lambda: scene.selection_ops.join_with_line(link=True))

        menu.addSeparator()

        self.transparent_action = self._action(menu, "👻 Make transparent","Make the selected shape translucent so you can see behind it",
                    w.on_transparent_toggled)
        self.transparent_action.setCheckable(True)
        self._action(menu, "📐 Quantize Selection","Move every selected point to the nearest grid line",w.snap_selection_to_grid)

        menu.addSeparator()

        self._action(menu, "🙈 Hide Selection","Hide the control points of the selected curve(s) — hover a curve if nothing is selected",
                     w.hide_selection)
        self._action(menu, "👁️ Show all points","Restore all hidden curve points", w.show_all_points)
        self._add_menu_button("✨ Effects", menu)

    def _build_settings(self):
        act = self.addAction("⚙️ Settings")
        act.setToolTip("Open settings dialog")
        act.triggered.connect(self.window.open_settings_dialog)

    def _build_right_group(self):
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        act = self.addAction("⌨️ Shortcuts")
        act.setToolTip("Show all keyboard shortcuts")
        act.triggered.connect(self.window.show_shortcuts)

        self.addAction("🗑️ Clear All").triggered.connect(self.window.clear_scene)

    # ------------------------------------------------------------
    #  Public sync API (called by MainWindow)
    # ------------------------------------------------------------
    def sync_mode(self, mode: str):
        """Reflect scene.mode without re-firing set_mode."""
        target = 0 if mode == "create" else 1
        if self.mode_combo.currentIndex() != target:
            self._set_quietly(self.mode_combo, target)

    def sync_zoom(self, factor: float):
        """Reflect a zoom the view applied on its own (Ctrl+wheel)."""
        for i in range(self.zoom_combo.count()):
            if self.zoom_combo.itemData(i) == factor:
                self._set_quietly(self.zoom_combo, i)
                return

    def step_zoom(self, direction: int) -> bool:
        idx = self.zoom_combo.currentIndex()
        new_idx = max(0, min(self.zoom_combo.count() - 1, idx + direction))
        if new_idx != idx:
            self.zoom_combo.setCurrentIndex(new_idx)
        return True

    @staticmethod
    def _set_quietly(combo, index):
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    # ------------------------------------------------------------
    #  Widget slots
    # ------------------------------------------------------------
    def _on_mode_changed(self, index):
        self.window.set_mode(self.mode_combo.itemData(index))

    def _on_zoom_changed(self, index):
        self.window.drawing_view.set_zoom(self.zoom_combo.itemData(index))

    def _on_degree_changed(self, index):
        data = self.degree_combo.itemData(index)
        if data is None:
            return
        degree, is_stroke = data
        self.scene.builder.set_curve_style(degree, is_stroke)

    def _on_grid_toggled(self, checked: bool):
        self.grid_action.setText("Hide Grid" if checked else "Show Grid")
        self.scene.grid_item.setVisible(checked)

    def _on_grid_size_changed(self, index: int):
        self.scene.grid_item.set_spacing(self.grid_combo.itemData(index))