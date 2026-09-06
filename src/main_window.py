# main_window.py
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView,
                               QPlainTextEdit, QFileDialog, QMessageBox)
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QPainter, QFont, QActionGroup
from PySide6.QtSvgWidgets import QSvgWidget
from settings import CANVAS_WIDTH, CANVAS_HEIGHT, PREVIEW_WIDTH, PREVIEW_HEIGHT, CODE_EDIT_HEIGHT
from bezier_scene import BezierScene

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bézier SVG Creator")
        self.resize(CANVAS_WIDTH + PREVIEW_WIDTH, CANVAS_HEIGHT + CODE_EDIT_HEIGHT + 50)

        # Central widget and main layout
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- Top row: Canvas + Preview ----
        top_row = QHBoxLayout()
        top_row.setSpacing(5)

        # Zone 1: Drawing canvas
        self.drawing_view = QGraphicsView()
        self.drawing_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.drawing_view.setFixedSize(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.scene = BezierScene()
        self.drawing_view.setScene(self.scene)
        top_row.addWidget(self.drawing_view)

        # Zone 3: SVG preview
        self.preview_widget = QSvgWidget()
        self.preview_widget.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview_widget.setStyleSheet("background-color: white;")
        top_row.addWidget(self.preview_widget)

        main_layout.addLayout(top_row)

        # ---- Bottom row: SVG code editor ----
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFixedHeight(CODE_EDIT_HEIGHT)
        self.code_edit.setFont(QFont("Courier New", 10))
        self.code_edit.setReadOnly(True)
        main_layout.addWidget(self.code_edit)

        # ---- Toolbar ----
        self.setup_toolbar()

        # Connect scene signal
        self.scene.svgCodeChanged.connect(self.update_preview_and_code)

        # Set initial mode and emit first SVG
        self.set_mode("create")
        self.scene.emit_svg()

    # ------------------------------------------------------------
    #  Toolbar setup
    # ------------------------------------------------------------
    def setup_toolbar(self):
        toolbar = self.addToolBar("Tools")

        # Create / Edit actions (mutually exclusive)
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

        # Clear All
        clear_action = toolbar.addAction("🗑️ Clear All")
        clear_action.triggered.connect(self.clear_scene)

        # Export SVG
        export_action = toolbar.addAction("💾 Export SVG")
        export_action.triggered.connect(self.export_svg)

    # ------------------------------------------------------------
    #  Mode switching: changes view drag behavior
    # ------------------------------------------------------------
    def set_mode(self, mode):
        self.scene.mode = mode
        if mode == "create":
            self.drawing_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.statusBar().showMessage("Create mode: click to place points. Drag background to pan.")
        else:  # edit
            self.drawing_view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.statusBar().showMessage("Edit mode: drag the blue/yellow points to reshape the curve.")

    # ------------------------------------------------------------
    #  Update preview + code
    # ------------------------------------------------------------
    def update_preview_and_code(self, svg_string):
        self.preview_widget.load(QByteArray(svg_string.encode()))
        self.code_edit.setPlainText(svg_string)

    # ------------------------------------------------------------
    #  Clear scene
    # ------------------------------------------------------------
    def clear_scene(self):
        self.scene.clear_all()

    # ------------------------------------------------------------
    #  Export to SVG file
    # ------------------------------------------------------------
    def export_svg(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save SVG", "", "SVG files (*.svg)"
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(self.scene.generate_svg())
                self.statusBar().showMessage(f"✅ Exported to {filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")