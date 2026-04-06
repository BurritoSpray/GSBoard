import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QScrollArea, QLineEdit, QLabel, QFileDialog, QMenu,
    QColorDialog, QMessageBox, QSizePolicy, QInputDialog, QFrame,
    QLayout, QApplication
)
from PyQt6.QtCore import (
    Qt, QSize, pyqtSignal, QRect, QPoint, QTimer, QMimeData, QByteArray
)
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QDrag

from gsboard.models.sound import Sound

SUPPORTED_EXTS = {".wav", ".flac", ".ogg", ".mp3", ".aiff", ".aif"}
_MIME_PATH = "application/x-gsboard-sound-path"
_BTN_W = 158
_BTN_H = 90


# ---------------------------------------------------------------------------
# Flow layout
# ---------------------------------------------------------------------------

class FlowLayout(QLayout):
    """Left-to-right wrapping layout — items flow like words in a paragraph."""

    def __init__(self, parent=None, spacing: int = 10):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), dry_run=True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, dry_run=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        s = QSize()
        for item in self._items:
            s = s.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        s += QSize(m.left() + m.right(), m.top() + m.bottom())
        return s

    def _do_layout(self, rect: QRect, dry_run: bool) -> int:
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        row_h = 0
        sp = self.spacing()
        right = rect.right() - m.right()

        for item in self._items:
            iw = item.sizeHint().width()
            ih = item.sizeHint().height()
            if x + iw > right and row_h > 0:
                x = rect.x() + m.left()
                y += row_h + sp
                row_h = 0
            if not dry_run:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x += iw + sp
            row_h = max(row_h, ih)

        return y + row_h - rect.y() + m.bottom()


# ---------------------------------------------------------------------------
# Sound button
# ---------------------------------------------------------------------------

class SoundButton(QFrame):
    play_requested = pyqtSignal(object)   # Sound
    stop_requested = pyqtSignal(object)   # Sound
    right_clicked = pyqtSignal(object)    # SoundButton

    def __init__(self, sound: Sound, parent=None):
        super().__init__(parent)
        self.sound = sound
        self.setFixedSize(_BTN_W, _BTN_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._playing = False
        self._hover = False
        self._drag_pos = None

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(10, 9, 10, 7)
        vbox.setSpacing(4)

        self._name_lbl = QLabel()
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._name_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._name_lbl.setStyleSheet(
            "color: white; font-size: 12px; font-weight: bold; background: transparent;"
        )
        vbox.addWidget(self._name_lbl, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(0)

        self._sc_lbl = QLabel()
        self._sc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._sc_lbl.setStyleSheet(
            "color: rgba(255,255,255,175); font-size: 9px; background: transparent;"
        )
        foot.addWidget(self._sc_lbl)
        foot.addStretch()

        self._vol_lbl = QLabel()
        self._vol_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._vol_lbl.setStyleSheet(
            "color: rgba(255,255,255,140); font-size: 9px; background: transparent;"
        )
        foot.addWidget(self._vol_lbl)
        vbox.addLayout(foot)

        self._sync_meta()
        self._restyle()

    # ---- Data sync ----

    def _sync_meta(self):
        self._name_lbl.setText(self.sound.name)
        sc = self.sound.shortcut
        self._sc_lbl.setText(sc or "")
        vol = int(self.sound.volume * 100)
        self._vol_lbl.setText(f"{vol}%" if vol != 100 else "")
        self.setToolTip(self.sound.name + (f"\n{sc}" if sc else ""))

    def _restyle(self):
        color = self.sound.color or "#4a90d9"
        if self._playing:
            bg = _lighten(color, 0.15)
            border = "3px solid rgba(255,255,255,220)"
            radius = "10px"
        elif self._hover:
            bg = _lighten(color, 0.08)
            border = "2px solid rgba(255,255,255,90)"
            radius = "10px"
        else:
            bg = color
            border = "2px solid rgba(0,0,0,40)"
            radius = "10px"

        self.setStyleSheet(f"""
            SoundButton {{
                background-color: {bg};
                border: {border};
                border-radius: {radius};
            }}
        """)

    def set_playing(self, playing: bool):
        if playing == self._playing:
            return
        self._playing = playing
        self._restyle()

    def update_sound(self, sound: Sound):
        self.sound = sound
        self._sync_meta()
        self._restyle()

    # ---- Qt events ----

    def enterEvent(self, e):
        self._hover = True
        self._restyle()

    def leaveEvent(self, e):
        self._hover = False
        self._restyle()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self)
        elif e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.pos()
        e.accept()

    def mouseMoveEvent(self, e):
        if (
            self._drag_pos is not None
            and (e.pos() - self._drag_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._drag_pos = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(_MIME_PATH, QByteArray(self.sound.file_path.encode()))
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            if self._playing:
                self.stop_requested.emit(self.sound)
            else:
                self.play_requested.emit(self.sound)
        e.accept()


# ---------------------------------------------------------------------------
# Sound grid
# ---------------------------------------------------------------------------

class SoundGrid(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.setAcceptDrops(True)
        self._buttons: list[SoundButton] = []
        self._build_ui()

        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_playing)
        self._poll.start(150)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search sounds...")
        self._search.textChanged.connect(self._filter)
        top.addWidget(self._search)

        add_btn = QPushButton("+ Add Sound")
        add_btn.clicked.connect(self._add_sound_dialog)
        top.addWidget(add_btn)

        scan_btn = QPushButton("Scan Folder")
        scan_btn.clicked.connect(self._scan_folder)
        top.addWidget(scan_btn)

        stop_btn = QPushButton("■  Stop All")
        stop_btn.clicked.connect(self.app_controller.stop_all)
        stop_btn.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; border-radius: 4px;"
            " padding: 4px 12px; font-weight: bold; }"
            "QPushButton:hover { background-color: #e53935; }"
            "QPushButton:pressed { background-color: #b71c1c; }"
        )
        top.addWidget(stop_btn)
        root.addLayout(top)

        # Scroll area with flow layout
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._flow_widget = QWidget()
        self._flow = FlowLayout(self._flow_widget, spacing=10)
        self._flow.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self._flow_widget)
        root.addWidget(scroll)

        self._drop_hint = QLabel("Drop audio files here or click '+ Add Sound'")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setStyleSheet("color: #888; font-size: 13px; padding: 20px;")
        root.addWidget(self._drop_hint)

        self.refresh()

    # ---- Playback polling ----

    def _poll_playing(self):
        engine = self.app_controller.engine
        for btn in self._buttons:
            btn.set_playing(engine.is_playing(btn.sound.name))

    # ---- Refresh / rebuild ----

    def refresh(self):
        self._rebuild_flow(self.app_controller.config.sounds)

    def _rebuild_flow(self, sounds):
        while self._flow.count():
            item = self._flow.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

        for sound in sounds:
            btn = SoundButton(sound)
            btn.play_requested.connect(self.app_controller.play_sound)
            btn.stop_requested.connect(
                lambda s: self.app_controller.engine.stop_sound(s.name)
            )
            btn.right_clicked.connect(self._show_context_menu)
            self._flow.addWidget(btn)
            self._buttons.append(btn)

        self._drop_hint.setVisible(len(sounds) == 0)
        self._flow_widget.updateGeometry()

    def _filter(self, text: str):
        q = text.lower()
        self._rebuild_flow([
            s for s in self.app_controller.config.sounds if q in s.name.lower()
        ])

    # ---- Add / import ----

    def _add_sound_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Sounds", "",
            "Audio Files (*.wav *.flac *.ogg *.mp3 *.aiff *.aif);;All Files (*)"
        )
        for p in paths:
            self._import_file(p)
        if paths:
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()

    def _scan_folder(self):
        folder = self.app_controller.config.sounds_folder
        if not folder or not Path(folder).is_dir():
            QMessageBox.warning(
                self, "Scan Folder",
                "No valid sounds folder configured.\nGo to Settings to set one."
            )
            return
        existing = {s.file_path for s in self.app_controller.config.sounds}
        count = 0
        for f in sorted(Path(folder).iterdir()):
            if f.suffix.lower() in SUPPORTED_EXTS and str(f) not in existing:
                self.app_controller.config.sounds.append(Sound(name=f.stem, file_path=str(f)))
                count += 1
        if count:
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()
        else:
            QMessageBox.information(self, "Scan Folder", "No new sounds found.")

    def _sounds_dir(self) -> Path:
        """Return the sounds directory, creating it if needed."""
        folder = self.app_controller.config.sounds_folder
        p = Path(folder) if folder else Path.home() / ".config" / "gsboard" / "sounds"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _import_file(self, path: str):
        src = Path(path)
        if src.suffix.lower() not in SUPPORTED_EXTS:
            return

        sounds_dir = self._sounds_dir()

        # If the file is already inside the sounds directory, use it as-is.
        try:
            src.relative_to(sounds_dir)
            dest = src
        except ValueError:
            # Copy to sounds directory, avoiding name collisions.
            dest = sounds_dir / src.name
            if dest.exists():
                stem, suffix = src.stem, src.suffix
                i = 2
                while dest.exists():
                    dest = sounds_dir / f"{stem}_{i}{suffix}"
                    i += 1
            shutil.copy2(src, dest)

        existing = {s.file_path for s in self.app_controller.config.sounds}
        if str(dest) not in existing:
            self.app_controller.config.sounds.append(Sound(name=dest.stem, file_path=str(dest)))

    # ---- Context menu ----

    def _show_context_menu(self, btn: SoundButton):
        menu = QMenu(self)
        rename_act = menu.addAction("Rename")
        color_act = menu.addAction("Set Color")
        volume_act = menu.addAction("Set Volume")
        menu.addSeparator()
        delete_act = menu.addAction("Delete")
        action = menu.exec(btn.mapToGlobal(btn.rect().center()))
        if action == rename_act:
            self._rename_sound(btn.sound)
        elif action == color_act:
            self._pick_color(btn.sound)
        elif action == volume_act:
            self._set_volume(btn.sound)
        elif action == delete_act:
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
            self.refresh()

    def _delete_sound(self, sound: Sound):
        reply = QMessageBox.question(
            self, "Delete Sound", f"Remove '{sound.name}' from library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.app_controller.config.sounds = [
                s for s in self.app_controller.config.sounds if s is not sound
            ]
            self.app_controller.save_config()
            self.app_controller.reload_hotkeys()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()

    # ---- Drag & drop ----

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasFormat(_MIME_PATH) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MIME_PATH) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasFormat(_MIME_PATH):
            # Internal reorder — disabled while a search is active
            if self._search.text():
                event.ignore()
                return
            src_path = event.mimeData().data(_MIME_PATH).data().decode()
            drop_pos = event.position().toPoint()
            target_idx = self._drop_target_idx(drop_pos)
            sounds = self.app_controller.config.sounds
            src_idx = next(
                (i for i, s in enumerate(sounds) if s.file_path == src_path), None
            )
            if src_idx is None or src_idx == target_idx:
                event.ignore()
                return
            sound = sounds.pop(src_idx)
            insert_at = target_idx if target_idx <= src_idx else target_idx - 1
            sounds.insert(insert_at, sound)
            self.app_controller.save_config()
            self.refresh()
            self.app_controller.main_window.shortcut_editor.refresh()
            event.acceptProposedAction()

        elif event.mimeData().hasUrls():
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

    def _drop_target_idx(self, drop_pos: QPoint) -> int:
        """Return the button index closest to drop_pos (in SoundGrid coordinates)."""
        if not self._buttons:
            return 0
        best_idx = len(self._buttons)
        best_dist = float("inf")
        for i, btn in enumerate(self._buttons):
            # btn lives in _flow_widget; convert its center to our coordinate space
            center_global = self._flow_widget.mapToGlobal(
                btn.pos() + QPoint(btn.width() // 2, btn.height() // 2)
            )
            center_local = self.mapFromGlobal(center_global)
            dist = (drop_pos - center_local).manhattanLength()
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return best_idx


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _lighten(hex_color: str, amount: float = 0.15) -> str:
    try:
        c = QColor(hex_color)
        h, s, v, a = c.getHsvF()
        c.setHsvF(h, max(0.0, s - amount), min(1.0, v + amount), a)
        return c.name()
    except Exception:
        return hex_color


def _darken(hex_color: str, amount: float = 0.15) -> str:
    try:
        c = QColor(hex_color)
        h, s, v, a = c.getHsvF()
        c.setHsvF(h, min(1.0, s + amount), max(0.0, v - amount), a)
        return c.name()
    except Exception:
        return hex_color
