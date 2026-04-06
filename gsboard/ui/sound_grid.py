import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QScrollArea, QLineEdit, QLabel, QFileDialog, QMenu, QDialog,
    QColorDialog, QMessageBox, QSizePolicy, QInputDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent

from gsboard.models.sound import Sound

SUPPORTED_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif"}


class SoundButton(QPushButton):
    right_clicked = pyqtSignal(object)

    def __init__(self, sound: Sound, parent=None):
        super().__init__(parent)
        self.sound = sound
        self.setFixedSize(QSize(120, 70))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_style()

    def _apply_style(self):
        color = self.sound.color or "#4a90d9"
        self.setText(self.sound.name)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border-radius: 6px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {_lighten(color)};
            }}
            QPushButton:pressed {{
                background-color: {_darken(color)};
            }}
            """
        )
        shortcut = self.sound.shortcut
        tooltip = f"{self.sound.name}"
        if shortcut:
            tooltip += f"\n[{shortcut}]"
        self.setToolTip(tooltip)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self)
        else:
            super().mousePressEvent(event)

    def update_sound(self, sound: Sound):
        self.sound = sound
        self._apply_style()


class SoundGrid(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.setAcceptDrops(True)
        self._buttons = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        top_bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search sounds...")
        self._search.textChanged.connect(self._filter)
        top_bar.addWidget(self._search)

        add_btn = QPushButton("+ Add Sound")
        add_btn.clicked.connect(self._add_sound_dialog)
        top_bar.addWidget(add_btn)

        scan_btn = QPushButton("Scan Folder")
        scan_btn.clicked.connect(self._scan_folder)
        top_bar.addWidget(scan_btn)

        stop_btn = QPushButton("Stop All")
        stop_btn.clicked.connect(self.app_controller.stop_all)
        stop_btn.setStyleSheet("background-color: #c62828; color: white; border-radius: 4px;")
        top_bar.addWidget(stop_btn)

        layout.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(8)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll)

        self._drop_label = QLabel("Drop audio files here or click '+ Add Sound'")
        self._drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_label.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(self._drop_label)

        self.refresh()

    def refresh(self):
        self._rebuild_grid(self.app_controller.config.sounds)

    def _rebuild_grid(self, sounds):
        for btn in self._buttons:
            self._grid.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

        for i, sound in enumerate(sounds):
            btn = SoundButton(sound)
            btn.clicked.connect(lambda checked, s=sound: self.app_controller.play_sound(s))
            btn.right_clicked.connect(self._show_context_menu)
            self._grid.addWidget(btn, i // 6, i % 6)
            self._buttons.append(btn)

        self._drop_label.setVisible(len(sounds) == 0)

    def _filter(self, text: str):
        query = text.lower()
        filtered = [
            s for s in self.app_controller.config.sounds
            if query in s.name.lower()
        ]
        self._rebuild_grid(filtered)

    def _add_sound_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Sounds", "",
            "Audio Files (*.wav *.flac *.ogg *.mp3 *.aiff *.aif);;All Files (*)"
        )
        for path in paths:
            self._import_file(path)
        if paths:
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()

    def _scan_folder(self):
        folder = self.app_controller.config.sounds_folder
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(self, "Scan Folder", "No valid sounds folder configured.\nGo to Settings to set one.")
            return
        count = 0
        existing = {s.file_path for s in self.app_controller.config.sounds}
        for f in sorted(Path(folder).iterdir()):
            if f.suffix.lower() in SUPPORTED_EXTS and str(f) not in existing:
                self.app_controller.config.sounds.append(
                    Sound(name=f.stem, file_path=str(f))
                )
                count += 1
        if count:
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()
        else:
            QMessageBox.information(self, "Scan Folder", "No new sounds found.")

    def _import_file(self, path: str):
        p = Path(path)
        if p.suffix.lower() not in SUPPORTED_EXTS:
            return
        existing = {s.file_path for s in self.app_controller.config.sounds}
        if path not in existing:
            self.app_controller.config.sounds.append(
                Sound(name=p.stem, file_path=path)
            )

    def _show_context_menu(self, btn: SoundButton):
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        color_action = menu.addAction("Set Color")
        volume_action = menu.addAction("Set Volume")
        menu.addSeparator()
        delete_action = menu.addAction("Delete")

        action = menu.exec(btn.mapToGlobal(btn.rect().center()))
        if action == rename_action:
            self._rename_sound(btn.sound)
        elif action == color_action:
            self._pick_color(btn.sound)
        elif action == volume_action:
            self._set_volume(btn.sound)
        elif action == delete_action:
            self._delete_sound(btn.sound)

    def _rename_sound(self, sound: Sound):
        name, ok = QInputDialog.getText(self, "Rename Sound", "New name:", text=sound.name)
        if ok and name.strip():
            sound.name = name.strip()
            self.app_controller.save_config()
            self.refresh()

    def _pick_color(self, sound: Sound):
        color = QColorDialog.getColor(QColor(sound.color), self, "Pick Color")
        if color.isValid():
            sound.color = color.name()
            self.app_controller.save_config()
            self.refresh()

    def _set_volume(self, sound: Sound):
        val, ok = QInputDialog.getDouble(
            self, "Set Volume", "Volume (0.0 – 1.0):",
            value=sound.volume, min=0.0, max=1.0, decimals=2,
        )
        if ok:
            sound.volume = val
            self.app_controller.save_config()

    def _delete_sound(self, sound: Sound):
        reply = QMessageBox.question(
            self, "Delete Sound",
            f"Remove '{sound.name}' from library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.app_controller.config.sounds = [
                s for s in self.app_controller.config.sounds if s is not sound
            ]
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        added = False
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTS:
                self._import_file(path)
                added = True
        if added:
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()


def _lighten(hex_color: str, amount: float = 0.15) -> str:
    try:
        c = QColor(hex_color)
        h, s, v, a = c.getHsvF()
        c.setHsvF(h, max(0, s - amount), min(1, v + amount), a)
        return c.name()
    except Exception:
        return hex_color


def _darken(hex_color: str, amount: float = 0.15) -> str:
    try:
        c = QColor(hex_color)
        h, s, v, a = c.getHsvF()
        c.setHsvF(h, min(1, s + amount), max(0, v - amount), a)
        return c.name()
    except Exception:
        return hex_color
