from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QHeaderView, QAbstractItemView, QCheckBox, QComboBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from gsboard.models.game_profile import GameProfile
from gsboard.models.sound import MacroConfig


class GameProfileDialog(QDialog):
    """Dialog for adding / editing a game profile."""

    def __init__(self, profile: GameProfile = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Game Profile" if profile else "Add Game Profile")
        self.setMinimumWidth(350)
        self._profile = profile or GameProfile()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name_edit = QLineEdit(self._profile.name)
        self._name_edit.setPlaceholderText("e.g. ARC Raiders")
        form.addRow("Profile name:", self._name_edit)

        self._proc_edit = QLineEdit(self._profile.process_name)
        self._proc_edit.setPlaceholderText("e.g. arc_raider.exe")
        form.addRow("Process name:", self._proc_edit)

        self._key_edit = QLineEdit(self._profile.macro.key)
        self._key_edit.setPlaceholderText("e.g.  b  or  f1")
        form.addRow("Macro key:", self._key_edit)

        self._pre_spin = QSpinBox()
        self._pre_spin.setRange(0, 10000)
        self._pre_spin.setSuffix(" ms")
        self._pre_spin.setValue(self._profile.macro.pre_delay_ms)
        form.addRow("Pre-delay:", self._pre_spin)

        self._post_spin = QSpinBox()
        self._post_spin.setRange(0, 10000)
        self._post_spin.setSuffix(" ms")
        self._post_spin.setValue(self._profile.macro.post_delay_ms)
        form.addRow("Post-delay:", self._post_spin)

        layout.addLayout(form)

        info = QLabel(
            "Process name: the executable name as seen in the system (e.g. arc_raider.exe).\n"
            "When this process is detected, the macro settings above will be used\n"
            "as the global macro for all sounds."
        )
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_profile(self) -> GameProfile:
        return GameProfile(
            name=self._name_edit.text().strip(),
            process_name=self._proc_edit.text().strip(),
            macro=MacroConfig(
                key=self._key_edit.text().strip(),
                pre_delay_ms=self._pre_spin.value(),
                post_delay_ms=self._post_spin.value(),
            ),
            enabled=self._profile.enabled,
        )


class GamesTab(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # -- Auto-detection toggle --
        detect_row = QHBoxLayout()
        self._detect_chk = QCheckBox("Enable automatic game detection")
        self._detect_chk.toggled.connect(self._on_detection_toggled)
        detect_row.addWidget(self._detect_chk)
        detect_row.addStretch()
        layout.addLayout(detect_row)

        # -- Status --
        self._status_label = QLabel()
        self._status_label.setStyleSheet("font-size: 12px; padding: 4px;")
        layout.addWidget(self._status_label)

        # -- Manual override --
        manual_row = QHBoxLayout()
        manual_row.addWidget(QLabel("Manual override:"))
        self._manual_combo = QComboBox()
        self._manual_combo.setMinimumWidth(200)
        self._manual_combo.currentIndexChanged.connect(self._on_manual_changed)
        manual_row.addWidget(self._manual_combo)
        manual_row.addStretch()
        layout.addLayout(manual_row)

        manual_info = QLabel(
            "Select a profile to force its macro regardless of which game is running. "
            "Set to 'Auto' to use process detection."
        )
        manual_info.setWordWrap(True)
        manual_info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(manual_info)

        # -- Separator --
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444;")
        layout.addWidget(sep)

        # -- Game profiles table --
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Enabled", "Name", "Process", "Macro Key", "Delays"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table)

        # -- Buttons --
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Profile")
        add_btn.clicked.connect(self._add_profile)
        btn_row.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_profile)
        btn_row.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_profile)
        btn_row.addWidget(remove_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def refresh(self):
        config = self.app_controller.config
        self._detect_chk.blockSignals(True)
        self._detect_chk.setChecked(config.game_detection_enabled)
        self._detect_chk.blockSignals(False)

        self._refresh_manual_combo()
        self._refresh_table()
        self._update_status()

    def _refresh_manual_combo(self):
        self._manual_combo.blockSignals(True)
        self._manual_combo.clear()
        self._manual_combo.addItem("Auto", "")
        config = self.app_controller.config
        selected_idx = 0
        for i, profile in enumerate(config.game_profiles):
            self._manual_combo.addItem(profile.name or profile.process_name, profile.name)
            if config.manual_game_profile and config.manual_game_profile == profile.name:
                selected_idx = i + 1
        self._manual_combo.setCurrentIndex(selected_idx)
        self._manual_combo.blockSignals(False)

    def _refresh_table(self):
        profiles = self.app_controller.config.game_profiles
        self._table.setRowCount(len(profiles))
        for row, profile in enumerate(profiles):
            chk = QCheckBox()
            chk.setChecked(profile.enabled)
            chk.toggled.connect(lambda checked, r=row: self._on_enabled_toggled(r, checked))
            chk_container = QWidget()
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.addWidget(chk)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            self._table.setCellWidget(row, 0, chk_container)

            self._table.setItem(row, 1, QTableWidgetItem(profile.name))
            self._table.setItem(row, 2, QTableWidgetItem(profile.process_name))
            self._table.setItem(row, 3, QTableWidgetItem(profile.macro.key or "(none)"))

            delays = f"{profile.macro.pre_delay_ms}ms / {profile.macro.post_delay_ms}ms"
            self._table.setItem(row, 4, QTableWidgetItem(delays))

    def _update_status(self):
        config = self.app_controller.config
        if config.manual_game_profile:
            profile = self._find_profile(config.manual_game_profile)
            if profile:
                self._status_label.setText(
                    f"Manual override active: {profile.name} (key: {profile.macro.key or 'none'})"
                )
                self._status_label.setStyleSheet("color: #f57c00; font-size: 12px; padding: 4px;")
                return

        if not config.game_detection_enabled:
            self._status_label.setText("Game detection is disabled.")
            self._status_label.setStyleSheet("color: #888; font-size: 12px; padding: 4px;")
            return

        detector = getattr(self.app_controller, 'game_detector', None)
        if detector and detector.active_profile:
            p = detector.active_profile
            self._status_label.setText(
                f"Detected: {p.name} (key: {p.macro.key}, "
                f"pre: {p.macro.pre_delay_ms}ms, post: {p.macro.post_delay_ms}ms)"
            )
            self._status_label.setStyleSheet("color: #4caf50; font-size: 12px; padding: 4px;")
        else:
            self._status_label.setText("No matching game detected.")
            self._status_label.setStyleSheet("color: #888; font-size: 12px; padding: 4px;")

    def _find_profile(self, name: str):
        for p in self.app_controller.config.game_profiles:
            if p.name == name:
                return p
        return None

    def _on_detection_toggled(self, checked: bool):
        self.app_controller.config.game_detection_enabled = checked
        self.app_controller.save_config()
        self.app_controller.reload_game_detection()
        self._update_status()

    def _on_manual_changed(self, index: int):
        name = self._manual_combo.currentData() or ""
        self.app_controller.config.manual_game_profile = name
        self.app_controller.save_config()
        self.app_controller.apply_game_macro()
        self._update_status()

    def _on_enabled_toggled(self, row: int, checked: bool):
        profiles = self.app_controller.config.game_profiles
        if row < len(profiles):
            profiles[row].enabled = checked
            self.app_controller.save_config()
            self.app_controller.reload_game_detection()

    def _add_profile(self):
        dlg = GameProfileDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            profile = dlg.get_profile()
            if not profile.name:
                QMessageBox.warning(self, "Invalid", "Profile name cannot be empty.")
                return
            self.app_controller.config.game_profiles.append(profile)
            self.app_controller.save_config()
            self.app_controller.reload_game_detection()
            self.refresh()

    def _edit_profile(self):
        row = self._table.currentRow()
        profiles = self.app_controller.config.game_profiles
        if row < 0 or row >= len(profiles):
            return
        dlg = GameProfileDialog(profiles[row], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated = dlg.get_profile()
            if not updated.name:
                QMessageBox.warning(self, "Invalid", "Profile name cannot be empty.")
                return
            profiles[row] = updated
            self.app_controller.save_config()
            self.app_controller.reload_game_detection()
            self.refresh()

    def _remove_profile(self):
        row = self._table.currentRow()
        profiles = self.app_controller.config.game_profiles
        if row < 0 or row >= len(profiles):
            return
        result = QMessageBox.question(
            self, "Remove Profile",
            f"Remove profile '{profiles[row].name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            profiles.pop(row)
            self.app_controller.save_config()
            self.app_controller.reload_game_detection()
            self.refresh()
