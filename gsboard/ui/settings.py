from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QSlider, QPushButton, QCheckBox, QLineEdit,
    QFileDialog, QGroupBox, QSpinBox, QScrollArea, QMessageBox
)
from gsboard.ui.shortcut_editor import ShortcutCaptureButton
from PyQt6.QtCore import Qt


class SettingsPanel(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self._build_ui()
        self._populate()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # --- Sounds folder ---
        folder_group = QGroupBox("Sound Library")
        folder_layout = QHBoxLayout(folder_group)
        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        folder_layout.addWidget(self._folder_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_folder)
        folder_layout.addWidget(browse_btn)
        layout.addWidget(folder_group)

        # --- Audio devices ---
        audio_group = QGroupBox("Audio Routing")
        audio_form = QFormLayout(audio_group)

        output_hint = QLabel(
            "Select your headset/speakers here — sounds will play locally "
            "so you can hear them. They are also routed to the virtual mics below."
        )
        output_hint.setWordWrap(True)
        output_hint.setStyleSheet("color: #aaa; font-size: 11px;")
        audio_form.addRow(output_hint)

        self._output_combo = QComboBox()
        audio_form.addRow("Monitor Output (headset):", self._output_combo)

        refresh_btn = QPushButton("Refresh Devices")
        refresh_btn.clicked.connect(self._refresh_devices)
        audio_form.addRow("", refresh_btn)

        audio_form.addRow(QLabel(""))

        self._mic_combo = QComboBox()
        audio_form.addRow("Your Real Microphone:", self._mic_combo)

        self._passthrough_check = QCheckBox(
            "Mix my voice into both virtual mics (game + chat)"
        )
        self._passthrough_check.toggled.connect(self._toggle_passthrough)
        audio_form.addRow("", self._passthrough_check)

        self._mic_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._mic_vol_slider.setRange(0, 100)
        self._mic_vol_slider.setValue(100)
        self._mic_vol_slider.valueChanged.connect(self._mic_vol_changed)
        audio_form.addRow("Mic Passthrough Volume:", self._mic_vol_slider)

        layout.addWidget(audio_group)

        # --- Master volume ---
        vol_group = QGroupBox("Playback")
        vol_form = QFormLayout(vol_group)

        self._master_vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._master_vol_slider.setRange(0, 100)
        self._master_vol_slider.setValue(100)
        self._master_vol_slider.valueChanged.connect(self._master_vol_changed)
        vol_form.addRow("Master Volume:", self._master_vol_slider)

        self._monitor_check = QCheckBox("Hear sounds in my headset (monitor loopback)")
        vol_form.addRow(self._monitor_check)

        self._loopback_shortcut_btn = ShortcutCaptureButton(
            on_open=self.app_controller.hotkey_manager.suspend,
            on_close=self.app_controller.hotkey_manager.resume,
        )
        vol_form.addRow("Toggle Loopback shortcut:", self._loopback_shortcut_btn)

        self._stop_all_shortcut_btn = ShortcutCaptureButton(
            on_open=self.app_controller.hotkey_manager.suspend,
            on_close=self.app_controller.hotkey_manager.resume,
        )
        vol_form.addRow("Stop All Sounds shortcut:", self._stop_all_shortcut_btn)

        layout.addWidget(vol_group)

        # --- Channel controls ---
        ch_group = QGroupBox("Output Channels")
        ch_form = QFormLayout(ch_group)

        ch_hint = QLabel(
            "Each channel is a separate virtual microphone. "
            "Select <b>GSBoard Game Mic</b> in your game and <b>GSBoard Chat Mic</b> in Discord. "
            "Use shortcuts to mute/unmute each channel independently."
        )
        ch_hint.setWordWrap(True)
        ch_hint.setStyleSheet("color: #aaa; font-size: 11px;")
        ch_form.addRow(ch_hint)

        # Game channel row
        self._game_check = QCheckBox("Game Mic enabled")
        self._game_check.toggled.connect(self._game_toggled)
        self._game_shortcut_btn = ShortcutCaptureButton(
            on_open=self.app_controller.hotkey_manager.suspend,
            on_close=self.app_controller.hotkey_manager.resume,
        )
        game_row = QHBoxLayout()
        game_row.addWidget(self._game_check)
        game_row.addStretch()
        game_row.addWidget(QLabel("Toggle shortcut:"))
        game_row.addWidget(self._game_shortcut_btn)
        ch_form.addRow("Game:", game_row)

        self._game_status = QLabel()
        ch_form.addRow("", self._game_status)

        # Chat channel row
        self._chat_check = QCheckBox("Chat Mic enabled")
        self._chat_check.toggled.connect(self._chat_toggled)
        self._chat_shortcut_btn = ShortcutCaptureButton(
            on_open=self.app_controller.hotkey_manager.suspend,
            on_close=self.app_controller.hotkey_manager.resume,
        )
        chat_row = QHBoxLayout()
        chat_row.addWidget(self._chat_check)
        chat_row.addStretch()
        chat_row.addWidget(QLabel("Toggle shortcut:"))
        chat_row.addWidget(self._chat_shortcut_btn)
        ch_form.addRow("Chat:", chat_row)

        self._chat_status = QLabel()
        ch_form.addRow("", self._chat_status)

        layout.addWidget(ch_group)

        # --- Virtual mic control ---
        vm_group = QGroupBox("Virtual Microphone")
        vm_layout = QVBoxLayout(vm_group)

        self._vm_status_label = QLabel()
        self._vm_status_label.setWordWrap(True)
        vm_layout.addWidget(self._vm_status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        create_btn = QPushButton("Create Virtual Mic")
        create_btn.clicked.connect(self._create_virtual_mic)
        btn_row.addWidget(create_btn)
        destroy_btn = QPushButton("Destroy Virtual Mic")
        destroy_btn.clicked.connect(self._destroy_virtual_mic)
        btn_row.addWidget(destroy_btn)
        vm_layout.addLayout(btn_row)

        layout.addWidget(vm_group)

        # --- Behavior ---
        behavior_group = QGroupBox("Behavior")
        behavior_form = QFormLayout(behavior_group)
        self._minimize_to_tray_check = QCheckBox(
            "Minimize to tray when closing the window (quit from tray menu)"
        )
        behavior_form.addRow(self._minimize_to_tray_check)
        layout.addWidget(behavior_group)

        layout.addStretch()

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        layout.addWidget(apply_btn)

        # Wire immediate conflict detection for all shortcut buttons
        for label, btn in self._settings_shortcut_buttons():
            btn.shortcut_captured.connect(
                lambda sc, b=btn, lbl=label: self._on_settings_shortcut_captured(b, lbl, sc)
            )

    def _populate(self):
        cfg = self.app_controller.config
        self._folder_edit.setText(cfg.sounds_folder or "")
        self._master_vol_slider.setValue(int(cfg.master_volume * 100))
        self._monitor_check.setChecked(cfg.monitor_enabled)
        self._mic_vol_slider.setValue(int(cfg.mic_passthrough_volume * 100))
        self._passthrough_check.setChecked(cfg.mic_passthrough)
        self._game_check.setChecked(cfg.channel_game_enabled)
        self._chat_check.setChecked(cfg.channel_chat_enabled)
        self._game_shortcut_btn.set_shortcut(cfg.channel_game_shortcut)
        self._chat_shortcut_btn.set_shortcut(cfg.channel_chat_shortcut)
        self._stop_all_shortcut_btn.set_shortcut(cfg.stop_all_shortcut)
        self._loopback_shortcut_btn.set_shortcut(cfg.loopback_shortcut)
        self._minimize_to_tray_check.setChecked(cfg.minimize_to_tray)
        self._refresh_devices()
        self._update_vm_status()
        self.refresh_channel_status()

    def _refresh_devices(self):
        cfg = self.app_controller.config
        ac = self.app_controller.audio_controller

        self._output_combo.clear()
        sinks = ac.list_output_devices()
        selected_index = 0
        for name, desc in sinks:
            if name == ac.game_sink_id:
                label = f"{desc}  ★ (GSBoard Game)"
            elif name == ac.chat_sink_id:
                label = f"{desc}  ★ (GSBoard Chat)"
            else:
                label = desc
            self._output_combo.addItem(label, name)
            if name == ac.game_sink_id:
                selected_index = self._output_combo.count() - 1
        if not sinks:
            self._output_combo.addItem("(no output devices found)", None)

        target = cfg.output_device or ac.game_sink_id
        for i in range(self._output_combo.count()):
            if self._output_combo.itemData(i) == target:
                self._output_combo.setCurrentIndex(i)
                break
        else:
            self._output_combo.setCurrentIndex(selected_index)

        self._mic_combo.clear()
        self._mic_combo.addItem("(none)", None)
        sources = ac.list_input_devices()
        for name, desc in sources:
            if name not in (ac.game_source_id, ac.chat_source_id):
                self._mic_combo.addItem(desc, name)
        if cfg.mic_device:
            for i in range(self._mic_combo.count()):
                if self._mic_combo.itemData(i) == cfg.mic_device:
                    self._mic_combo.setCurrentIndex(i)

    def _settings_shortcut_buttons(self):
        """Return (label, button) pairs for all shortcut buttons in the Settings panel."""
        return [
            ("Toggle Game Mic",  self._game_shortcut_btn),
            ("Toggle Chat Mic",  self._chat_shortcut_btn),
            ("Stop All Sounds",  self._stop_all_shortcut_btn),
            ("Toggle Loopback",  self._loopback_shortcut_btn),
        ]

    def _saved_shortcut_for(self, btn) -> str:
        """Return the currently saved config value for the given button."""
        cfg = self.app_controller.config
        if btn is self._game_shortcut_btn:
            return cfg.channel_game_shortcut
        if btn is self._chat_shortcut_btn:
            return cfg.channel_chat_shortcut
        if btn is self._stop_all_shortcut_btn:
            return cfg.stop_all_shortcut
        if btn is self._loopback_shortcut_btn:
            return cfg.loopback_shortcut
        return ""

    def _on_settings_shortcut_captured(self, btn, label, new_sc):
        if not new_sc:
            return
        old_sc = self._saved_shortcut_for(btn)
        # Check against saved config
        conflict = self.app_controller.find_shortcut_conflict(new_sc, exclude=old_sc)
        # Also check unsaved sibling buttons in this panel
        if not conflict:
            for sibling_label, sibling_btn in self._settings_shortcut_buttons():
                if sibling_btn is not btn and sibling_btn.get_shortcut() == new_sc:
                    conflict = sibling_label
                    break
        if not conflict:
            return
        result = QMessageBox.question(
            self, "Shortcut Conflict",
            f"<b>{new_sc}</b> is already used by <b>{conflict}</b>.<br><br>"
            f"Overwrite and assign to <b>{label}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self.app_controller.clear_shortcut(new_sc)
            for _, sibling_btn in self._settings_shortcut_buttons():
                if sibling_btn is not btn and sibling_btn.get_shortcut() == new_sc:
                    sibling_btn.set_shortcut("")
        else:
            btn.set_shortcut(old_sc)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Sounds Folder")
        if folder:
            self._folder_edit.setText(folder)

    def _toggle_passthrough(self, checked: bool):
        pass

    def _mic_vol_changed(self, value: int):
        pass

    def _master_vol_changed(self, value: int):
        self.app_controller.engine.set_master_volume(value / 100)
        self.app_controller.config.master_volume = value / 100

    def _game_toggled(self, checked: bool):
        pass  # applied on Apply

    def _chat_toggled(self, checked: bool):
        pass  # applied on Apply

    def _apply(self):
        cfg = self.app_controller.config

        cfg.sounds_folder = self._folder_edit.text()
        cfg.output_device = self._output_combo.currentData()
        cfg.mic_device = self._mic_combo.currentData()
        cfg.mic_passthrough = self._passthrough_check.isChecked()
        cfg.mic_passthrough_volume = self._mic_vol_slider.value() / 100
        cfg.master_volume = self._master_vol_slider.value() / 100
        cfg.monitor_enabled = self._monitor_check.isChecked()
        self.app_controller.engine.set_monitor_enabled(cfg.monitor_enabled)
        cfg.channel_game_enabled = self._game_check.isChecked()
        cfg.channel_chat_enabled = self._chat_check.isChecked()
        cfg.channel_game_shortcut = self._game_shortcut_btn.get_shortcut()
        cfg.channel_chat_shortcut = self._chat_shortcut_btn.get_shortcut()
        cfg.stop_all_shortcut = self._stop_all_shortcut_btn.get_shortcut()
        cfg.loopback_shortcut = self._loopback_shortcut_btn.get_shortcut()
        cfg.minimize_to_tray = self._minimize_to_tray_check.isChecked()
        self.app_controller.save_config()
        self.app_controller.apply_audio_settings()
        self.app_controller.reload_hotkeys()
        self._update_vm_status()
        self.refresh_channel_status()

    def _create_virtual_mic(self):
        ok = self.app_controller.audio_controller.create_virtual_devices()
        self._update_vm_status()
        if not ok:
            from PyQt6.QtWidgets import QMessageBox
            from PyQt6.QtCore import Qt
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Virtual Mic")
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            box.setText(
                "Failed to create virtual audio devices.<br>"
                "On Linux: is PipeWire running?<br>"
                'On Windows: install '
                '<a href="https://vb-audio.com/Cable/">VB-Cable</a>.'
            )
            box.exec()
        else:
            self.app_controller.apply_audio_settings()

    def _destroy_virtual_mic(self):
        self.app_controller.audio_controller.destroy_virtual_devices()
        self._update_vm_status()

    def _update_vm_status(self):
        ac = self.app_controller.audio_controller
        lines = []

        for sink_active, src_active, source_id, label in [
            (ac.is_game_sink_active(), ac.is_game_source_active(),
             ac.game_source_id, "Game"),
            (ac.is_chat_sink_active(), ac.is_chat_source_active(),
             ac.chat_source_id, "Chat"),
        ]:
            if sink_active and src_active:
                lines.append(
                    f"<span style='color:#4caf50'>✔ {label}: {source_id} (active)</span>"
                )
            elif sink_active:
                lines.append(
                    f"<span style='color:#ff9800'>⚠ {label}: sink active, mic source missing</span>"
                )
            else:
                lines.append(
                    f"<span style='color:#f44336'>✘ {label}: inactive</span>"
                )

        self._vm_status_label.setText("<br>".join(lines))

    def refresh_loopback_status(self):
        self._monitor_check.blockSignals(True)
        self._monitor_check.setChecked(self.app_controller.config.monitor_enabled)
        self._monitor_check.blockSignals(False)

    def refresh_channel_status(self):
        engine = self.app_controller.engine
        ac = self.app_controller.audio_controller

        game_on = engine.is_game_enabled()
        self._game_status.setText(
            f"Mic: <b>{ac.game_source_id}</b> — "
            + ("<span style='color:#4caf50'>sending sounds</span>" if game_on
               else "<span style='color:#888'>muted</span>")
        )

        chat_on = engine.is_chat_enabled()
        self._chat_status.setText(
            f"Mic: <b>{ac.chat_source_id}</b> — "
            + ("<span style='color:#4caf50'>sending sounds</span>" if chat_on
               else "<span style='color:#888'>muted</span>")
        )
