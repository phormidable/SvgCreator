"""UserSettings: persistent user preferences stored in user_settings.json at the project root."""

import json
from pathlib import Path
from PySide6.QtGui import QColor


class UserSettings:
    """Manages user preferences in a JSON file at the project root.

    Settings include:
    - json_dir: default directory for saving JSON files
    - svg_dir: default directory for saving SVG files
    - curve_color: default color for new curves
    - stroke_size: default stroke width for stroke curves
    - canvas_width, canvas_height: default canvas dimensions
    """

    SETTINGS_FILE = Path(__file__).parent.parent.parent / "user_settings.json"

    def __init__(self):
        self._json_dir = ""
        self._svg_dir = ""
        self._curve_color = "#5a5a5a"  # Default gray
        self._stroke_start_width = 250  # Changed from _stroke_size
        self._stroke_end_width = 250  # New
        self._canvas_width = 1024
        self._canvas_height = 1024
        self._load()

    def _load(self):
        """Load settings from JSON file if it exists."""
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._json_dir = data.get("json_dir", "")
                self._svg_dir = data.get("svg_dir", "")
                self._curve_color = data.get("curve_color", "#5a5a5a")
                self._stroke_size = data.get("stroke_size", 250)
                self._canvas_width = data.get("canvas_width", 1024)
                self._canvas_height = data.get("canvas_height", 1024)
            except Exception as e:
                print(f"Warning: Could not load user settings: {e}")

    def _save(self):
        """Save current settings to JSON file."""
        try:
            data = {
                "json_dir": self._json_dir,
                "svg_dir": self._svg_dir,
                "curve_color": self._curve_color,
                "stroke_start_width": self._stroke_start_width,
                "stroke_end_width": self._stroke_end_width,
                "canvas_width": self._canvas_width,
                "canvas_height": self._canvas_height,
            }
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save user settings: {e}")

    # ------------------------------------------------------------
    #  Properties with auto-save
    # ------------------------------------------------------------
    @property
    def json_dir(self) -> str:
        return self._json_dir

    @json_dir.setter
    def json_dir(self, value: str):
        self._json_dir = (value or "").strip()
        self._save()

    @property
    def svg_dir(self) -> str:
        return self._svg_dir

    @svg_dir.setter
    def svg_dir(self, value: str):
        self._svg_dir = (value or "").strip()
        self._save()

    @property
    def curve_color(self) -> str:
        return self._curve_color

    @curve_color.setter
    def curve_color(self, value: str):
        self._curve_color = (value or "#5a5a5a").strip()
        self._save()

    @property
    def stroke_size(self) -> int:
        return self._stroke_size

    @stroke_size.setter
    def stroke_size(self, value: int):
        self._stroke_size = max(1, min(5000, int(value)))
        self._save()

    @property
    def canvas_width(self) -> int:
        return self._canvas_width

    @canvas_width.setter
    def canvas_width(self, value: int):
        self._canvas_width = max(100, min(2000, int(value)))
        self._save()

    @property
    def canvas_height(self) -> int:
        return self._canvas_height

    @canvas_height.setter
    def canvas_height(self, value: int):
        self._canvas_height = max(100, min(2000, int(value)))
        self._save()

    @property
    def stroke_start_width(self) -> int:
        return self._stroke_start_width

    @stroke_start_width.setter
    def stroke_start_width(self, value: int):
        self._stroke_start_width = max(1, min(5000, int(value)))
        self._save()

    @property
    def stroke_end_width(self) -> int:
        return self._stroke_end_width

    @stroke_end_width.setter
    def stroke_end_width(self, value: int):
        self._stroke_end_width = max(1, min(5000, int(value)))
        self._save()

    def update_all(self, json_dir: str, svg_dir: str, curve_color: str,
                   stroke_start_width: int, stroke_end_width: int, canvas_width: int, canvas_height: int):
        self._json_dir = (json_dir or "").strip()
        self._svg_dir = (svg_dir or "").strip()
        self._curve_color = (curve_color or "#5a5a5a").strip()
        self._stroke_start_width = max(1, min(5000, int(stroke_start_width)))
        self._stroke_end_width = max(1, min(5000, int(stroke_end_width)))
        self._canvas_width = max(100, min(2000, int(canvas_width)))
        self._canvas_height = max(100, min(2000, int(canvas_height)))
        self._save()