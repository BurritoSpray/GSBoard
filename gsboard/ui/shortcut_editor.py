from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QHeaderView, QAbstractItemView, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QKeyEvent

from gsboard.models.sound import Sound, MacroConfig

# Maps Qt Key values (when KeypadModifier is set) to pynput-style numpad names.
_NUMPAD_KEY_NAMES = {
    Qt.Key.Key_0: "num_0",
    Qt.Key.Key_1: "num_1",
    Qt.Key.Key_2: "num_2",
    Qt.Key.Key_3: "num_3",
    Qt.Key.Key_4: "num_4",
    Qt.Key.Key_5: "num_5",
    Qt.Key.Key_6: "num_6",
    Qt.Key.Key_7: "num_7",
    Qt.Key.Key_8: "num_8",
    Qt.Key.Key_9: "num_9",
    Qt.Key.Key_Period: "num_decimal",
    Qt.Key.Key_Plus: "num_add",
    Qt.Key.Key_Minus: "num_subtract",
    Qt.Key.Key_Asterisk: "num_multiply",
    Qt.Key.Key_Slash: "num_divide",
    Qt.Key.Key_Enter: "num_enter",
}


class ShortcutCaptureDialog(QDialog):
    """Modal dialog that captures a single key combination."""

    def __init__(self, current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Shortcut")
        self.setModal(True)
        self.setFixedSize(320, 140)
        self._shortcut = current

        layout = QVBoxLayout(self)
        self._label = QLabel("Press any key combination, then release.\nEsc to cancel.")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        self._result_label = QLabel(current or "—")
        self._result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 8px;")
        layout.addWidget(self._result_label)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _clear(self):
        self._shortcut = ""
        self.accept()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            event.accept()
            self.reject()
            return
        # ignore bare modifier presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            event.accept()
            return
        modifiers = event.modifiers()
        is_numpad = bool(modifiers & Qt.KeyboardModifier.KeypadModifier)
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("<ctrl>")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("<shift>")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("<alt>")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("<super>")
        if is_numpad:
            key_name = _NUMPAD_KEY_NAMES.get(key, QKeySequence(key).toString().lower())
        else:
            key_name = QKeySequence(key).toString().lower()
        if key_name and key_name not in ("ctrl", "shift", "alt", "meta", ""):
            if not key_name.startswith("<"):
                key_name = f"<{key_name}>" if len(key_name) > 1 else key_name
            parts.append(key_name)
        event.accept()
        if parts:
            self._shortcut = "+".join(parts)
            self._result_label.setText(self._shortcut)
            self.accept()

    def get_shortcut(self) -> str:
        return self._shortcut


class ShortcutCaptureButton(QPushButton):
    shortcut_captured = pyqtSignal(str)

    def __init__(self, initial: str = "", parent=None, on_open=None, on_close=None):
        super().__init__(parent)
        self._shortcut = initial
        self._on_open = on_open
        self._on_close = on_close
        self._update_text()
        self.clicked.connect(self._open_dialog)

    def _update_text(self):
        self.setText(self._shortcut if self._shortcut else "Click to set...")

    def _open_dialog(self):
        if self._on_open:
            self._on_open()
        try:
            dlg = ShortcutCaptureDialog(self._shortcut, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._shortcut = dlg.get_shortcut()
                self._update_text()
                self.shortcut_captured.emit(self._shortcut)
        finally:
            if self._on_close:
                self._on_close()

    def get_shortcut(self) -> str:
        return self._shortcut

    def set_shortcut(self, s: str):
        self._shortcut = s
        self._update_text()


class MacroDialog(QDialog):
    def __init__(self, sound: Sound, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Macro — {sound.name}")
        self.sound = sound
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._key_edit = QLineEdit(self.sound.macro.key)
        self._key_edit.setPlaceholderText("e.g.  b  or  f1")
        form.addRow("Key to hold:", self._key_edit)

        self._pre_spin = QSpinBox()
        self._pre_spin.setRange(0, 10000)
        self._pre_spin.setSuffix(" ms")
        self._pre_spin.setValue(self.sound.macro.pre_delay_ms)
        form.addRow("Pre-sound delay:", self._pre_spin)

        self._post_spin = QSpinBox()
        self._post_spin.setRange(0, 10000)
        self._post_spin.setSuffix(" ms")
        self._post_spin.setValue(self.sound.macro.post_delay_ms)
        form.addRow("Post-sound delay:", self._post_spin)

        layout.addLayout(form)

        info = QLabel(
            "Leave key empty to disable the macro.\n"
            "Pre-delay: time before the sound starts.\n"
            "Post-delay: extra hold after the sound ends."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)
        layout.addLayout(btn_row)

    def _reset(self):
        self._key_edit.clear()
        self._pre_spin.setValue(0)
        self._post_spin.setValue(0)

    def get_macro(self) -> MacroConfig:
        return MacroConfig(
            key=self._key_edit.text().strip(),
            pre_delay_ms=self._pre_spin.value(),
            post_delay_ms=self._post_spin.value(),
        )


class ShortcutEditor(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # -- Global macro section --
        gm_label = QLabel("Global Macro")
        gm_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(gm_label)

        gm_info = QLabel(
            "Applied to all sounds that don't have their own macro configured."
        )
        gm_info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(gm_info)

        gm_form = QHBoxLayout()
        gm_form.setSpacing(8)

        gm_form.addWidget(QLabel("Key:"))
        self._gm_key = QLineEdit()
        self._gm_key.setPlaceholderText("e.g.  b  or  f1")
        self._gm_key.setMaximumWidth(100)
        gm_form.addWidget(self._gm_key)

        gm_form.addWidget(QLabel("Pre-delay:"))
        self._gm_pre = QSpinBox()
        self._gm_pre.setRange(0, 10000)
        self._gm_pre.setSuffix(" ms")
        gm_form.addWidget(self._gm_pre)

        gm_form.addWidget(QLabel("Post-delay:"))
        self._gm_post = QSpinBox()
        self._gm_post.setRange(0, 10000)
        self._gm_post.setSuffix(" ms")
        gm_form.addWidget(self._gm_post)

        gm_apply = QPushButton("Apply")
        gm_apply.clicked.connect(self._apply_global_macro)
        gm_form.addWidget(gm_apply)

        gm_form.addStretch()
        layout.addLayout(gm_form)

        # -- Separator --
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444;")
        layout.addWidget(sep)

        # -- Per-sound shortcuts --
        info = QLabel(
            "Click a shortcut cell to record a key combination. "
            "Click 'Macro' to configure key-hold timing."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Sound", "Shortcut", "Pass Through", "Macro Key", "Macro Delays"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

    def _apply_global_macro(self):
        self.app_controller.config.global_macro = MacroConfig(
            key=self._gm_key.text().strip(),
            pre_delay_ms=self._gm_pre.value(),
            post_delay_ms=self._gm_post.value(),
        )
        self.app_controller.save_config()

    def refresh(self):
        gm = self.app_controller.config.global_macro
        self._gm_key.setText(gm.key)
        self._gm_pre.setValue(gm.pre_delay_ms)
        self._gm_post.setValue(gm.post_delay_ms)

        sounds = self.app_controller.config.sounds
        self._table.setRowCount(len(sounds))
        for row, sound in enumerate(sounds):
            self._table.setItem(row, 0, QTableWidgetItem(sound.name))

            capture_btn = ShortcutCaptureButton(
                sound.shortcut,
                on_open=self.app_controller.hotkey_manager.suspend,
                on_close=self.app_controller.hotkey_manager.resume,
            )
            capture_btn.shortcut_captured.connect(
                lambda s, snd=sound: self._on_shortcut_captured(snd, s)
            )
            self._table.setCellWidget(row, 1, capture_btn)

            chk = QCheckBox()
            chk.setChecked(sound.shortcut_pass_through)
            chk.toggled.connect(lambda checked, snd=sound: self._on_pass_through_toggled(snd, checked))
            chk_container = QWidget()
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 2, chk_container)

            macro_key_item = QTableWidgetItem(sound.macro.key or "(none)")
            self._table.setItem(row, 3, macro_key_item)

            macro_edit_btn = QPushButton("Edit Macro")
            macro_edit_btn.clicked.connect(lambda _, snd=sound, r=row: self._edit_macro(snd, r))
            self._table.setCellWidget(row, 4, macro_edit_btn)

    def _on_shortcut_captured(self, sound: Sound, shortcut: str):
        if shortcut:
            conflict = self.app_controller.find_shortcut_conflict(shortcut, exclude=sound.shortcut)
            if conflict:
                result = QMessageBox.question(
                    self, "Shortcut Conflict",
                    f"<b>{shortcut}</b> is already used by <b>{conflict}</b>.<br><br>"
                    f"Overwrite and assign to <b>{sound.name}</b>?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if result != QMessageBox.StandardButton.Yes:
                    self.refresh()
                    return
                self.app_controller.clear_shortcut(shortcut)
        sound.shortcut = shortcut
        self.app_controller.save_config()
        self.app_controller.reload_hotkeys()
        self.refresh()

    def _on_pass_through_toggled(self, sound: Sound, checked: bool):
        sound.shortcut_pass_through = checked
        self.app_controller.save_config()
        self.app_controller.reload_hotkeys()

    def _edit_macro(self, sound: Sound, row: int):
        dialog = MacroDialog(sound, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            sound.macro = dialog.get_macro()
            self.app_controller.save_config()
            self._table.item(row, 3).setText(sound.macro.key or "(none)")
