import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt

from gsboard.models.config import AppConfig
from gsboard.audio.pipewire import PipeWireController
from gsboard.audio.engine import AudioEngine
from gsboard.input.hotkeys import HotkeyManager
from gsboard.macros.macro_engine import MacroEngine
from gsboard.models.sound import Sound


class AppController:
    def __init__(self):
        self.config = AppConfig()
        self.config.load()

        self.pipewire = PipeWireController(self.config.virtual_sink_name)
        self.engine = AudioEngine(self.pipewire)
        self.hotkey_manager = HotkeyManager()
        self.macro_engine = MacroEngine()

        self.main_window = None
        self._tray: QSystemTrayIcon = None

    def start(self):
        self.pipewire.create_virtual_sink()
        self.engine.set_master_volume(self.config.master_volume)
        self.engine.set_monitor_device(self.config.output_device)
        self.engine.set_game_enabled(self.config.channel_game_enabled)
        self.engine.set_chat_enabled(self.config.channel_chat_enabled)
        self._start_audio_streams()
        self.hotkey_manager.start()
        self.reload_hotkeys()

    def _start_audio_streams(self):
        # paplay targets sinks by their pactl name directly — no device lookup needed.
        self.engine.start()

    def apply_audio_settings(self):
        self.engine.stop()
        self._start_audio_streams()
        self.engine.set_master_volume(self.config.master_volume)
        self.engine.set_monitor_device(self.config.output_device)
        self.engine.set_game_enabled(self.config.channel_game_enabled)
        self.engine.set_chat_enabled(self.config.channel_chat_enabled)
        if self.config.mic_passthrough and self.config.mic_device:
            self.pipewire.enable_mic_passthrough(
                self.config.mic_device,
                self.config.mic_passthrough_volume,
            )
        else:
            self.pipewire.disable_mic_passthrough()

    def play_sound(self, sound: Sound):
        if sound.macro.key:
            self.macro_engine.execute(
                sound.macro,
                self.engine.play,
                sound.name,
                sound.file_path,
                sound.volume,
            )
        else:
            self.engine.play(sound.name, sound.file_path, sound.volume)

    def stop_all(self):
        self.engine.stop_all()

    def save_config(self):
        self.config.save()

    def reload_hotkeys(self):
        shortcuts = {}
        for sound in self.config.sounds:
            if sound.shortcut:
                shortcuts[sound.shortcut] = lambda s=sound: self.play_sound(s)
        if self.config.channel_game_shortcut:
            shortcuts[self.config.channel_game_shortcut] = self.toggle_game_channel
        if self.config.channel_chat_shortcut:
            shortcuts[self.config.channel_chat_shortcut] = self.toggle_chat_channel
        if self.config.stop_all_shortcut:
            shortcuts[self.config.stop_all_shortcut] = self.stop_all
        if self.config.loopback_shortcut:
            shortcuts[self.config.loopback_shortcut] = self.toggle_loopback
        self.hotkey_manager.set_shortcuts(shortcuts)
        self.hotkey_manager.start()

    def toggle_game_channel(self):
        enabled = not self.engine.is_game_enabled()
        self.engine.set_game_enabled(enabled)
        self.config.channel_game_enabled = enabled
        self.config.save()
        if self.main_window:
            self.main_window.refresh_channel_status()

    def toggle_loopback(self):
        enabled = not self.config.mic_passthrough
        self.config.mic_passthrough = enabled
        if enabled and self.config.mic_device:
            self.pipewire.enable_mic_passthrough(
                self.config.mic_device,
                self.config.mic_passthrough_volume,
            )
        else:
            self.pipewire.disable_mic_passthrough()
        self.config.save()

    def toggle_chat_channel(self):
        enabled = not self.engine.is_chat_enabled()
        self.engine.set_chat_enabled(enabled)
        self.config.channel_chat_enabled = enabled
        self.config.save()
        if self.main_window:
            self.main_window.refresh_channel_status()

    def on_quit(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        self.hotkey_manager.stop()
        self.engine.stop()
        self.pipewire.disable_mic_passthrough()
        self.pipewire.destroy_virtual_sink()
        self.macro_engine.shutdown()
        self.config.save()

    def setup_tray(self, app: QApplication):
        icon = _make_tray_icon()
        self._tray = QSystemTrayIcon(icon, app)
        menu = QMenu()
        show_action = menu.addAction("Show")
        show_action.triggered.connect(lambda: self.main_window.show() if self.main_window else None)
        stop_action = menu.addAction("Stop All Sounds")
        stop_action.triggered.connect(self.stop_all)
        menu.addSeparator()
        game_action = menu.addAction("Toggle Game Mic")
        game_action.triggered.connect(self.toggle_game_channel)
        chat_action = menu.addAction("Toggle Chat Mic")
        chat_action.triggered.connect(self.toggle_chat_channel)
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(lambda: (self.on_quit(), app.quit()))
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("GSBoard")
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window:
                if self.main_window.isVisible():
                    self.main_window.hide()
                else:
                    self.main_window.show()
                    self.main_window.raise_()


def _make_tray_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(QColor("#4a90d9"))
    return QIcon(px)
