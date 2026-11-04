from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
                               QPushButton, QColorDialog, QFormLayout, QSizePolicy, QCheckBox)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt


class SettingsPanel(QWidget):
    """Live-updating settings panel for the right-side tab.

    Changes apply immediately to the scene and persist to user_settings.json.
    """

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.scene = window.scene
        self.user_settings = window.user_settings
        self._build_ui()
        self._sync_from_settings()
        self._connect_selection_signals()

        # ------------------------------------------------------------
    #  UI construction
    # ------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        # ---- Stroke Width ----
        self.stroke_start_spin = QSpinBox()
        self.stroke_start_spin.setRange(1, 500)
        self.stroke_start_spin.setSuffix(" units")
        self.stroke_start_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.stroke_start_spin.valueChanged.connect(self._on_start_width_changed)

        self.stroke_end_spin = QSpinBox()
        self.stroke_end_spin.setRange(1, 500)
        self.stroke_end_spin.setSuffix(" units")
        self.stroke_end_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.stroke_end_spin.valueChanged.connect(self._on_end_width_changed)

        self.swap_btn = QPushButton("⇄")
        self.swap_btn.setToolTip("Swap start and end stroke widths")
        self.swap_btn.setFixedSize(32, 28)
        self.swap_btn.setStyleSheet(
            "QPushButton { font-size: 16px; font-weight: bold; margin: 0px; }"
            "QPushButton:hover { background-color: #d0d0d0; }"
        )
        self.swap_btn.clicked.connect(self._swap_stroke_widths)

        # NEW: Checkbox to enable/disable variable width
        self.variable_width_cb = QCheckBox()
        self.variable_width_cb.setToolTip("Enable variable stroke width (different start/end)")
        self.variable_width_cb.setChecked(True)  # Enabled by default
        self.variable_width_cb.stateChanged.connect(self._on_variable_width_toggled)


        begin_label = QLabel("Beginning:")
        begin_label.setContentsMargins(0, 0, 0, 0)
        end_label = QLabel("End:")
        end_label.setContentsMargins(0, 0, 0, 0)

        stroke_layout = QHBoxLayout()
        stroke_layout.setContentsMargins(0, 0, 0, 0)
        stroke_layout.setSpacing(8)
        stroke_layout.addWidget(begin_label)
        stroke_layout.addWidget(self.stroke_start_spin)
        stroke_layout.addStretch(1)
        stroke_layout.addWidget(self.swap_btn)
        stroke_layout.addStretch(1)
        stroke_layout.addWidget(self.variable_width_cb)
        stroke_layout.addWidget(end_label)
        stroke_layout.addWidget(self.stroke_end_spin)

        form.addRow("Stroke Width:", stroke_layout)

        # ---- Curve Color ----
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(80, 26)
        self.color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.color_btn.clicked.connect(self._on_color_clicked)
        form.addRow("Curve Color:", self.color_btn)

        # ---- NEW: Selection Z-order ----
        self.z_spin = QSpinBox()
        self.z_spin.setRange(-100, 100)
        self.z_spin.setSuffix("")
        self.z_spin.setToolTip(
            "Z-order of the selected curve/shape/chain.\n"
            "Higher values appear on top of lower values.")
        self.z_spin.setEnabled(False)  # Disabled until something is selected
        self.z_spin.valueChanged.connect(self._on_z_changed)

        form.addRow("Selection Z:", self.z_spin)

        layout.addLayout(form)
        layout.addStretch(1)  # Push content to top

    # ------------------------------------------------------------
    #  Sync UI <-> settings
    # ------------------------------------------------------------
    def _sync_from_settings(self):
        """Update UI widgets from current user_settings values (no signals fired)."""
        self.stroke_start_spin.blockSignals(True)
        self.stroke_end_spin.blockSignals(True)
        self.variable_width_cb.blockSignals(True)

        self.stroke_start_spin.setValue(self.user_settings.stroke_start_width)
        self.stroke_end_spin.setValue(self.user_settings.stroke_end_width)

        # Checkbox is checked if start != end
        is_variable = self.user_settings.stroke_start_width != self.user_settings.stroke_end_width
        self.variable_width_cb.setChecked(is_variable)
        self.stroke_end_spin.setEnabled(is_variable)

        self.stroke_start_spin.blockSignals(False)
        self.stroke_end_spin.blockSignals(False)
        self.variable_width_cb.blockSignals(False)
        self._update_color_button()

    def _update_color_button(self):
        color = self.user_settings.curve_color
        self.color_btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: 1px solid #888; }}"
            f"QPushButton:hover {{ border: 2px solid #cc3333; }}"
        )
        self.color_btn.setToolTip(f"Curve color: {color}")

    # ------------------------------------------------------------
    #  Slots
    # ------------------------------------------------------------
    def _on_start_width_changed(self, value):
        self.user_settings.stroke_start_width = value
        self.scene.stroke_start_width = value
        if self.scene.builder.current_start_width is not None:
            self.scene.builder.set_curve_style(
                self.scene.builder.current_degree, is_stroke=True)

    def _on_end_width_changed(self, value):
        self.user_settings.stroke_end_width = value
        self.scene.stroke_end_width = value
        if self.scene.builder.current_start_width is not None:
            self.scene.builder.set_curve_style(
                self.scene.builder.current_degree, is_stroke=True)

    def _swap_stroke_widths(self):
        start_val = self.stroke_start_spin.value()
        end_val = self.stroke_end_spin.value()
        self.stroke_start_spin.setValue(end_val)
        self.stroke_end_spin.setValue(start_val)

    def _on_color_clicked(self):
        current = QColor(self.user_settings.curve_color)
        color = QColorDialog.getColor(current, self, "Select Curve Color")
        if color.isValid():
            self.user_settings.curve_color = color.name()
            self.scene.set_curve_color(color)
            self._update_color_button()

    def _on_variable_width_toggled(self, state):
        """Enable/disable the end spinbox based on checkbox state."""
        is_enabled = state == Qt.CheckState.Checked.value
        self.stroke_end_spin.setEnabled(is_enabled)

        if not is_enabled:
            # When disabled, force end width to match start width
            self.stroke_end_spin.setValue(self.stroke_start_spin.value())
            # Trigger the update
            self._on_end_width_changed(self.stroke_end_spin.value())

    # ------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------
    def refresh_from_settings(self):
        """Call this when external code changes user_settings (e.g., main dialog)."""
        self._sync_from_settings()

    def _connect_selection_signals(self):
        """Listen for selection changes to update the Z spinbox."""
        sel = self.scene.selection
        # Connect to signals that indicate selection changed
        # (adjust signal names to match your Selection class)
        if hasattr(sel, 'selectionChanged'):
            sel.selectionChanged.connect(self._on_selection_changed)
        # Also refresh when curves are added/removed
        self.scene.document.curve_added.connect(self._on_selection_changed)
        self.scene.document.curve_deleted.connect(self._on_selection_changed)
        # Initial sync
        self._on_selection_changed()

    def _on_selection_changed(self, *_args):
        """Update the Z spinbox to reflect the current selection."""
        selected_curves = self._get_selected_curves()
        if not selected_curves:
            self.z_spin.blockSignals(True)
            self.z_spin.setEnabled(False)
            self.z_spin.setValue(0)
            self.z_spin.blockSignals(False)
            return

        # If all selected curves have the same Z, show it
        z_values = {int(c.zValue()) for c in selected_curves}
        self.z_spin.blockSignals(True)
        if len(z_values) == 1:
            self.z_spin.setValue(z_values.pop())
            self.z_spin.setEnabled(True)
        else:
            # Mixed Z values — show the first one but keep enabled
            self.z_spin.setValue(int(selected_curves[0].zValue()))
            self.z_spin.setEnabled(True)
        self.z_spin.blockSignals(False)

    def _get_selected_curves(self):
        """Return the list of curves affected by the current selection."""
        curves = set()
        # Collect curves from all selected points
        for pt in self.scene.selected_points:
            if pt.curve is not None:
                curves.add(pt.curve)
        # Also include the hovered curve if any
        if self.scene.selection.hovered_curve is not None:
            curves.add(self.scene.selection.hovered_curve)
        return list(curves)

    def _on_z_changed(self, value):
        """Apply the new Z value to all selected curves and update shape fills."""
        selected_curves = self._get_selected_curves()
        if not selected_curves:
            return

        for c in selected_curves:
            c.setZValue(value)
            c.update()

        # Update shape fill Z-values to match
        self.scene.shape_manager.update_shape_z_values()

        self.scene.emit_svg()