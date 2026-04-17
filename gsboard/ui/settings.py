from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QSlider, QPushButton, QCheckBox, QLineEdit,
    QFileDialog, QGroupBox, QSpinBox, QScrollArea, QMessageBox
)
from gsboard.ui.shortcut_editor import ShortcutCaptureButton
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer


class _NoWheelFilter(QObject):
    """Event filter that lets wheel events bubble up to the parent
    scroll area instead of being consumed by combos/sliders."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            event.ignore()
            return True
        return False


class SettingsPanel(QWidget):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self._no_wheel_filter = _NoWheelFilter(self)
        # Guards re-entry during _populate so programmatic setValue/setChecked
        # calls don't fire the auto-apply handlers.
        self._loading = True
        # Debounces config saves while the user is dragging a slider.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)
        self._save_timer.timeout.connect(self.app_controller.save_config)
        self._build_ui()
        self._install_no_wheel()
        self._populate()
        self._loading = False

    def _install_no_wheel(self):
        """Stop combos and sliders from stealing wheel events while the
        user is scrolling the Settings tab."""
        for cls in (QComboBox, QSlider, QSpinBox):
            for child in self.findChildren(cls):
                child.installEventFilter(self._no_wheel_filter)

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
        self._output_combo.currentIndexChanged.connect(self._output_changed)
        audio_form.addRow("Monitor Output (headset):", self._output_combo)

        refresh_btn = QPushButton("Refresh Devices")
        refresh_btn.clicked.connect(self._refresh_devices)
        audio_form.addRow("", refresh_btn)

        audio_form.addRow(QLabel(""))

        self._mic_combo = QComboBox()
        self._mic_combo.currentIndexChanged.connect(self._mic_changed)
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

        caps = self.app_controller.audio_controller.capabilities
        if not caps.supports_mic_passthrough:
            self._passthrough_check.setEnabled(False)
            self._mic_vol_slider.setEnabled(False)
            if caps.mic_passthrough_hint:
                self._passthrough_check.setToolTip(caps.mic_passthrough_hint)

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
        self._monitor_check.toggled.connect(self._monitor_toggled)
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

        ch_hint = QLabel(caps.channels_hint_html or "")
        ch_hint.setWordWrap(True)
        ch_hint.setOpenExternalLinks(True)
        ch_hint.setStyleSheet("color: #aaa; font-size: 11px;")
        ch_form.addRow(ch_hint)

        # Per-channel device mapping — only shown when the backend asks
        # the user to pick among external virtual cables.
        self._game_device_combo: Optional[QComboBox] = None
        self._chat_device_combo: Optional[QComboBox] = None
        if caps.supports_user_device_selection:
            self._game_device_combo = QComboBox()
            self._game_device_combo.currentIndexChanged.connect(
                lambda _i: self._channel_device_changed("game")
            )
            ch_form.addRow("Game device:", self._game_device_combo)

            self._chat_device_combo = QComboBox()
            self._chat_device_combo.currentIndexChanged.connect(
                lambda _i: self._channel_device_changed("chat")
            )
            ch_form.addRow("Chat device:", self._chat_device_combo)

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
        self._vm_status_label.setOpenExternalLinks(True)
        vm_layout.addWidget(self._vm_status_label)

        if caps.supports_virtual_device_management:
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            create_btn = QPushButton("Create Virtual Mic")
            create_btn.clicked.connect(self._create_virtual_mic)
            btn_row.addWidget(create_btn)
            destroy_btn = QPushButton("Destroy Virtual Mic")
            destroy_btn.clicked.connect(self._destroy_virtual_mic)
            btn_row.addWidget(destroy_btn)
            vm_layout.addLayout(btn_row)
        elif caps.setup_hint_html:
            setup_label = QLabel(caps.setup_hint_html)
            setup_label.setOpenExternalLinks(True)
            setup_label.setWordWrap(True)
            setup_label.setStyleSheet("color: #aaa; font-size: 11px;")
            vm_layout.addWidget(setup_label)

        layout.addWidget(vm_group)

        # --- Behavior ---
        behavior_group = QGroupBox("Behavior")
        behavior_form = QFormLayout(behavior_group)
        self._minimize_to_tray_check = QCheckBox(
            "Minimize to tray when closing the window (quit from tray menu)"
        )
        self._minimize_to_tray_check.toggled.connect(self._tray_toggled)
        behavior_form.addRow(self._minimize_to_tray_check)
        layout.addWidget(behavior_group)

        layout.addStretch()

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

        self._output_combo.blockSignals(True)
        self._output_combo.clear()
        sinks = ac.list_output_devices()
        cable_names = {n for n in (ac.game_sink_id, ac.chat_sink_id) if n}
        first_non_cable = -1
        for name, desc in sinks:
            if name == ac.game_sink_id:
                label = f"{desc}  ★ (GSBoard Game)"
            elif name == ac.chat_sink_id:
                label = f"{desc}  ★ (GSBoard Chat)"
            else:
                label = desc
            self._output_combo.addItem(label, name)
            if name not in cable_names and first_non_cable < 0:
                first_non_cable = self._output_combo.count() - 1
        if not sinks:
            self._output_combo.addItem("(no output devices found)", None)

        # Default to the first real headset/speaker, never VB-Cable.
        fallback = first_non_cable if first_non_cable >= 0 else 0

        target = cfg.output_device or ""
        if target in cable_names:
            # A VB-Cable can never be a valid monitor — the user wouldn't
            # hear anything. Treat leftover cable selections as "no choice".
            target = ""
        chosen = -1
        if target:
            for i in range(self._output_combo.count()):
                if self._output_combo.itemData(i) == target:
                    chosen = i
                    break
            # Legacy MME names get truncated to 31 chars; tolerate that so
            # a pre-WASAPI config doesn't silently lose the user's choice.
            if chosen < 0 and len(target) >= 20:
                for i in range(self._output_combo.count()):
                    data = self._output_combo.itemData(i) or ""
                    if data.startswith(target):
                        chosen = i
                        break
        self._output_combo.setCurrentIndex(chosen if chosen >= 0 else fallback)
        self._output_combo.blockSignals(False)

        self._mic_combo.blockSignals(True)
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
        self._mic_combo.blockSignals(False)

        self._refresh_channel_devices()

    def _refresh_channel_devices(self):
        """Populate the per-channel device dropdowns for backends that ask
        the user to pick among external virtual cables."""
        if self._game_device_combo is None or self._chat_device_combo is None:
            return
        ac = self.app_controller.audio_controller
        candidates = ac.list_channel_candidates()

        for combo, current in (
            (self._game_device_combo, ac.game_sink_id),
            (self._chat_device_combo, ac.chat_sink_id),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(none)", "")
            for device_id, display in candidates:
                combo.addItem(display, device_id)
            # Select the backend's current device, if still present.
            target_idx = 0
            for i in range(combo.count()):
                if combo.itemData(i) == (current or ""):
                    target_idx = i
                    break
            combo.setCurrentIndex(target_idx)
            combo.blockSignals(False)

    def _channel_device_changed(self, channel: str):
        combo = (self._game_device_combo if channel == "game"
                 else self._chat_device_combo)
        if combo is None:
            return
        device_id = combo.currentData() or None
        ac = self.app_controller.audio_controller
        ac.set_channel_device(channel, device_id)

        cfg = self.app_controller.config
        if channel == "game":
            cfg.channel_game_device = device_id or ""
        else:
            cfg.channel_chat_device = device_id or ""
        self.app_controller.save_config()
        self.app_controller.apply_audio_settings()
        self._update_vm_status()
        self.refresh_channel_status()
        if self.app_controller.main_window is not None:
            self.app_controller.main_window._update_status()

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
        if conflict:
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
                return
        self._commit_shortcuts()

    def _commit_shortcuts(self):
        """Write every shortcut button's value into config and restart
        the hotkey listener. Called after a capture (possibly post-conflict
        resolution)."""
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.channel_game_shortcut = self._game_shortcut_btn.get_shortcut()
        cfg.channel_chat_shortcut = self._chat_shortcut_btn.get_shortcut()
        cfg.stop_all_shortcut = self._stop_all_shortcut_btn.get_shortcut()
        cfg.loopback_shortcut = self._loopback_shortcut_btn.get_shortcut()
        self.app_controller.save_config()
        self.app_controller.reload_hotkeys()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Sounds Folder")
        if not folder:
            return
        self._folder_edit.setText(folder)
        self.app_controller.config.sounds_folder = folder
        self.app_controller.save_config()

    def _output_changed(self, _index: int):
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.output_device = self._output_combo.currentData()
        self.app_controller.engine.set_monitor_device(cfg.output_device)
        self.app_controller.save_config()

    def _mic_changed(self, _index: int):
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.mic_device = self._mic_combo.currentData()
        self.app_controller.save_config()
        self._apply_mic_passthrough()

    def _toggle_passthrough(self, checked: bool):
        if self._loading:
            return
        self.app_controller.config.mic_passthrough = checked
        self.app_controller.save_config()
        self._apply_mic_passthrough()

    def _mic_vol_changed(self, value: int):
        if self._loading:
            return
        self.app_controller.config.mic_passthrough_volume = value / 100
        # Live-update a running passthrough so the slider is responsive
        # without tearing down the stream on every tick.
        self.app_controller.audio_controller.set_mic_passthrough_volume(
            value / 100
        )
        self._save_timer.start()

    def _master_vol_changed(self, value: int):
        if self._loading:
            return
        self.app_controller.engine.set_master_volume(value / 100)
        self.app_controller.config.master_volume = value / 100
        self._save_timer.start()

    def _monitor_toggled(self, checked: bool):
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.monitor_enabled = checked
        self.app_controller.engine.set_monitor_enabled(checked)
        self.app_controller.save_config()

    def _game_toggled(self, checked: bool):
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.channel_game_enabled = checked
        self.app_controller.engine.set_game_enabled(checked)
        self.app_controller.save_config()
        self.refresh_channel_status()

    def _chat_toggled(self, checked: bool):
        if self._loading:
            return
        cfg = self.app_controller.config
        cfg.channel_chat_enabled = checked
        self.app_controller.engine.set_chat_enabled(checked)
        self.app_controller.save_config()
        self.refresh_channel_status()

    def _tray_toggled(self, checked: bool):
        if self._loading:
            return
        self.app_controller.config.minimize_to_tray = checked
        self.app_controller.save_config()

    def _apply_mic_passthrough(self):
        """(Re)start mic passthrough based on current config, or stop it."""
        cfg = self.app_controller.config
        ac = self.app_controller.audio_controller
        if cfg.mic_passthrough and cfg.mic_device:
            ac.enable_mic_passthrough(cfg.mic_device, cfg.mic_passthrough_volume)
        else:
            ac.disable_mic_passthrough()

    def _create_virtual_mic(self):
        ok = self.app_controller.audio_controller.create_virtual_devices()
        self._update_vm_status()
        if not ok:
            from PyQt6.QtCore import Qt
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("Virtual Mic")
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            box.setText(
                "Failed to create virtual audio devices.<br>"
                "Is PipeWire running?"
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

        for channel in ("game", "chat"):
            info = ac.get_channel_info(channel)
            if info.active:
                lines.append(
                    f"<span style='color:#4caf50'>✔ {info.label}: "
                    f"{info.device_name} (active)</span>"
                )
            elif info.short_state == "partial":
                lines.append(
                    f"<span style='color:#ff9800'>⚠ {info.unavailable_html}</span>"
                )
            elif info.short_state == "n/a":
                lines.append(
                    f"<span style='color:#888'>— {info.unavailable_html}</span>"
                )
            else:
                lines.append(
                    f"<span style='color:#f44336'>✘ {info.unavailable_html}</span>"
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
