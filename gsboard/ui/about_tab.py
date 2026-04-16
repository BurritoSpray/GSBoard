import os

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from gsboard import __version__ as VERSION
from gsboard.resources import resource_path
REPO_URL = "https://github.com/BurritoSpray/GSBoard"


class AboutTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Logo
        icon_path = resource_path("gsboard.png")
        if os.path.isfile(icon_path):
            logo_label = QLabel()
            pixmap = QPixmap(icon_path).scaled(
                128, 128,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        # App name and version
        name_label = QLabel(f"GSBoard  v{VERSION}")
        name_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # Repository link
        link_label = QLabel(f'<a href="{REPO_URL}">{REPO_URL}</a>')
        link_label.setOpenExternalLinks(True)
        link_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(link_label)
