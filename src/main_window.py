# main_window.py
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QColorDialog
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QActionGroup, QColor
from PySide6.QtSvgWidgets import QSvgWidget

from settings import DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT
from bezier_scene import BezierScene
from custom_view import CustomGraphicsView
from info_panel import InfoPanel
from file_io import FileIO

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bézier SVG Creator")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout: [ drawing ] | [ preview / info ]
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- Left column: drawing view (the main zone) ----
        self.drawing_view = CustomGraphicsView()
        self.drawing_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.drawing_view.setMinimumSize(DRAWING_MIN_WIDTH, DRAWING_MIN_HEIGHT)
        # no setFixedSize — let the layout stretch it
        self.scene = BezierScene()
        self.drawing_view.setScene(self.scene)
        main_layout.addWidget(self.drawing_view, 1)  # stretch = 1, take all the room
        self.file_io = FileIO(self)
        # ---- Right column: preview on top, info below ----
        right_col = QVBoxLayout()
        right_col.setSpacing(5)

        self.preview_widget = QSvgWidget()
        self.preview_widget.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_widget.setStyleSheet("background-color: white;")
        right_col.addWidget(self.preview_widget)

        self.info_panel = InfoPanel(self.scene)
        right_col.addWidget(self.info_panel, 1)

        main_layout.addLayout(right_col)

        # ---- Toolbar ----
        self._setup_toolbar()

        # ---- Mouse coordinate label ----
        self.coord_label = QLabel(self.drawing_view.viewport())
        self.coord_label.setStyleSheet(
            "background-color: rgba(0,0,0,180); color: white; "
            "padding: 2px 5px; border-radius: 3px; font-weight: bold;"
        )
        self.coord_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.coord_label.setText("(0.0, 0.0)")  # initial text
        self.coord_label.adjustSize()
        self.coord_label.move(10, 10)  # initial position
        self.coord_label.show()  # show from the start
        self.coord_label.raise_()  # ensure it's on top

        # ---- Connect signals ----
        self.scene.svgCodeChanged.connect(self.update_preview)
        self.drawing_view.mouseMoved.connect(self.show_mouse_coordinates)
        self.drawing_view.mouseMoved.connect(self.scene.on_mouse_moved)

        # Initial state
        self.set_mode("create")
        self.scene.emit_svg()

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.scene.clear_selection()
            if self.scene.cancel_pending_curve():
                event.accept()
                return
        elif key == Qt.Key.Key_L:
            if self.scene.link_manager.try_link_proximity():
                event.accept()
                return
        elif key == Qt.Key.Key_S:
            if self.scene.shape_manager.select_from_hover():
                event.accept()
                return
        elif key == Qt.Key.Key_C:
            self.color_selected_shape()
            event.accept()
            return
        elif key == Qt.Key.Key_H:
            if self.scene.hide_hovered_curve_points():
                event.accept()
                return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            dx = -1 if key == Qt.Key.Key_Left else 1 if key == Qt.Key.Key_Right else 0
            dy = -1 if key == Qt.Key.Key_Up else 1 if key == Qt.Key.Key_Down else 0
            if self.scene.move_selected_points(dx, dy):
                event.accept()
                return

        super().keyPressEvent(event)

    def log(self, message: str):
        self.info_panel.log(message)

    # ------------------------------------------------------------
    #  Mouse coordinate label
    # ------------------------------------------------------------
    def show_mouse_coordinates(self, scene_pos):
        if scene_pos is None:
            self.coord_label.hide()
            return

        text = f"({scene_pos.x():.1f}, {scene_pos.y():.1f})"
        self.coord_label.setText(text)
        self.coord_label.adjustSize()

        vp = self.drawing_view.mapFromScene(scene_pos)
        x = vp.x() + 15
        y = vp.y() + 15
        max_x = self.drawing_view.width() - self.coord_label.width()
        max_y = self.drawing_view.height() - self.coord_label.height()
        x = min(max(x, 0), max_x)
        y = min(max(y, 0), max_y)
        self.coord_label.move(x, y)
        self.coord_label.show()
        self.coord_label.raise_()

    # ------------------------------------------------------------
    #  Toolbar
    # ------------------------------------------------------------
    def _setup_toolbar(self):
        toolbar = self.addToolBar("Tools")

        self.create_action = toolbar.addAction("✏️ Create")
        self.create_action.setCheckable(True)
        self.edit_action = toolbar.addAction("🖱️ Edit")
        self.edit_action.setCheckable(True)

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addAction(self.create_action)
        self.mode_group.addAction(self.edit_action)
        self.create_action.setChecked(True)

        self.create_action.triggered.connect(lambda: self.set_mode("create"))
        self.edit_action.triggered.connect(lambda: self.set_mode("edit"))

        toolbar.addSeparator()

        # Zoom
        self.zoom_group = QActionGroup(self)
        self.zoom_group.setExclusive(True)
        self.zoom_actions = {}

        zoom_levels = [
            ("0.5x", 0.5, "Ctrl+1"),
            ("1x", 1.0, "Ctrl+2"),
            ("2x", 2.0, "Ctrl+3"),
            ("4x", 4.0, "Ctrl+4"),
            ("8x", 8.0, "Ctrl+5"),
            ("16x", 16.0, "Ctrl+6"),
        ]
        for label, factor, shortcut in zoom_levels:
            action = toolbar.addAction(label)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setToolTip(f"Zoom {label}  ({shortcut})")
            action.triggered.connect(lambda checked=False, f=factor: self.drawing_view.set_zoom(f))
            self.zoom_group.addAction(action)
            self.zoom_actions[factor] = action
        self.zoom_actions[1.0].setChecked(True)

        toolbar.addSeparator()
        bg_action = toolbar.addAction("🖼️ Add Background Image")
        bg_action.triggered.connect(self.file_io.load_background_image)
        toolbar.addSeparator()

        show_all_action = toolbar.addAction("👁️ Show All")
        show_all_action.setToolTip("Restore all hidden curve points")
        show_all_action.triggered.connect(self.show_all_points)

        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

        load_action = toolbar.addAction("📂 Load")
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.file_io.load_project)

        save_action = toolbar.addAction("💾 Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.file_io.save_project)

        toolbar.addSeparator()

        generate_action = toolbar.addAction("📄 Generate SVG code")
        generate_action.triggered.connect(self.file_io.show_svg_code_dialog)

        export_action = toolbar.addAction("💾 Export SVG")
        export_action.triggered.connect(self.file_io.export_svg)

    # ------------------------------------------------------------
    #  Mode switching
    # ------------------------------------------------------------
    def set_mode(self, mode):
        # If switching to Edit and there are incomplete points, discard them
        self.log(f"Mode → {mode}")
        if mode == "edit" and self.scene.pending_curve is not None:
            self.scene.discard_current_points()
            self.statusBar().showMessage("Incomplete curve discarded. Switch to Edit mode.")

        self.scene.set_selected_point(None)
        self.scene.mode = mode
        if mode == "create":
            self.statusBar().showMessage("Create mode: left-click to place points. Right-drag to pan.")
        else:
            self.statusBar().showMessage("Edit mode: drag points or edit coordinates. Right-drag to pan.")

        self.coord_label.show()

    # ------------------------------------------------------------
    #  Update preview & code
    # ------------------------------------------------------------
    def update_preview(self, svg_string):
        self.preview_widget.load(QByteArray(svg_string.encode()))

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()


    def show_all_points(self):
        n = self.scene.show_all_points()
        if n:
            self.statusBar().showMessage(f"👁️ Restored points on {n} curve(s)")
        else:
            self.statusBar().showMessage("Nothing to restore")

    def color_selected_shape(self):
        shape = self.scene.shape_manager.selected()
        if shape is None:
            self.statusBar().showMessage("No shape selected — hover a curve and press S first")
            return
        initial = shape.color if shape.color is not None else QColor(180, 180, 180)
        color = QColorDialog.getColor(initial, self, f"Color for {shape.name}")
        if not color.isValid():
            return
        self.scene.shape_manager.set_color(shape, color)
        self.log(f"{shape.name} colored {color.name()}")