import subprocess
import sys
from typing import Optional

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from gsboard.audio.backend import AudioController
from gsboard.audio.engine import AudioEngine
from gsboard.games.detector import ProcessDetector
from gsboard.input.hotkeys import SESSION_TYPE, HotkeyManager
from gsboard.macros.macro_engine import MacroEngine
from gsboard.models.config import AppConfig
from gsboard.models.game_profile import GameProfile
from gsboard.models.sound import MacroConfig, Sound
from gsboard.resources import resource_path


def _make_audio_controller(config: AppConfig) -> AudioController:
    """Select the appropriate AudioController for the current platform."""
    if sys.platform == "win32":
        from gsboard.audio.windows import WindowsAudioController

        return WindowsAudioController(
            game_sink=config.channel_game_device or None,
            chat_sink=config.channel_chat_device or None,
        )
    # Linux (PipeWire / PulseAudio)
    from gsboard.audio.pipewire import PipeWireController

    return PipeWireController(config.virtual_sink_name)


def _shortcut_to_tool_key(shortcut: str) -> Optional[str]:
    """Convert a pynput-style shortcut to an xdotool/ydotool key name."""
    _MOD = {
        "ctrl": "ctrl",
        "control": "ctrl",
        "alt": "alt",
        "shift": "shift",
        "super": "super",
        "meta": "super",
        "cmd": "super",
        "win": "super",
    }
    _KEYS = {
        "space": "space",
        "return": "Return",
        "enter": "Return",
        "escape": "Escape",
        "esc": "Escape",
        "backspace": "BackSpace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "page_up": "Page_Up",
        "page_down": "Page_Down",
        "up": "Up",
        "down": "Down",
        "left": "Left",
        "right": "Right",
        "tab": "Tab",
        "print_screen": "Print",
        "scroll_lock": "Scroll_Lock",
        "pause": "Pause",
        "caps_lock": "Caps_Lock",
        "num_lock": "Num_Lock",
    }

    modifiers = []
    key = None

    for part in shortcut.lower().split("+"):
        token = part.strip().strip("<>").strip()
        if not token:
            continue
        if token in _MOD:
            modifiers.append(_MOD[token])
        elif len(token) > 1 and token[0] == "f" and token[1:].isdigit():
            key = f"F{token[1:]}"
        elif len(token) == 1:
            key = token
        elif token in _KEYS:
            key = _KEYS[token]
        else:
            key = token  # best-effort pass-through of unknown names

    if key is None and not modifiers:
        return None
    return "+".join(modifiers + ([key] if key else []))


def _simulate_shortcut(shortcut: str) -> None:
    """Re-inject a shortcut key press (for pass-through after KGlobalAccel grab)."""
    key = _shortcut_to_tool_key(shortcut)
    if not key:
        return

    if SESSION_TYPE == "wayland":
        try:
            subprocess.run(
                ["ydotool", "key", key],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print(
                "[pass-through] ydotool not found — "
                "install ydotool and start ydotoold for Wayland key simulation"
            )
    else:
        try:
            subprocess.run(
                ["xdotool", "key", key],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("[pass-through] xdotool not found")


class AppController:
    def __init__(self):
        self.config = AppConfig()
        self.config.load()

        self.audio_controller: AudioController = _make_audio_controller(self.config)
        self.engine = AudioEngine(self.audio_controller)
        self.hotkey_manager = HotkeyManager()
        self.macro_engine = MacroEngine()
        self.game_detector = ProcessDetector()
        self.game_detector.set_callback(self._on_game_detected)
        self._game_macro_active: Optional[MacroConfig] = None

        self.main_window = None
        self._tray: QSystemTrayIcon = None

    def start(self):
        self.audio_controller.create_virtual_devices()
        # Sync any channel-device dedup done by the controller back into
        # config so the persisted state matches what the UI will display.
        if self.audio_controller.capabilities.supports_user_device_selection:
            self.config.channel_game_device = self.audio_controller.game_sink_id or ""
            self.config.channel_chat_device = self.audio_controller.chat_sink_id or ""
        self.engine.set_master_volume(self.config.master_volume)
        self.engine.set_monitor_device(self.config.output_device)
        self.engine.set_game_enabled(self.config.channel_game_enabled)
        self.engine.set_chat_enabled(self.config.channel_chat_enabled)
        self.engine.set_monitor_enabled(self.config.monitor_enabled)
        self._start_audio_streams()
        if self.config.mic_passthrough and self.config.mic_device:
            self.audio_controller.enable_mic_passthrough(
                self.config.mic_device,
                self.config.mic_passthrough_volume,
            )
        self.hotkey_manager.start()
        self.reload_hotkeys()
        self.reload_game_detection()

    def _start_audio_streams(self):
        self.engine.start()

    def apply_audio_settings(self):
        self.engine.stop()
        self._start_audio_streams()
        self.engine.set_master_volume(self.config.master_volume)
        self.engine.set_monitor_device(self.config.output_device)
        self.engine.set_game_enabled(self.config.channel_game_enabled)
        self.engine.set_chat_enabled(self.config.channel_chat_enabled)
        self.engine.set_monitor_enabled(self.config.monitor_enabled)
        if self.config.mic_passthrough and self.config.mic_device:
            self.audio_controller.enable_mic_passthrough(
                self.config.mic_device,
                self.config.mic_passthrough_volume,
            )
        else:
            self.audio_controller.disable_mic_passthrough()

    def _effective_global_macro(self) -> MacroConfig:
        """Return the global macro, considering game detection override."""
        if self._game_macro_active and self._game_macro_active.key:
            return self._game_macro_active
        return self.config.global_macro

    def play_sound(self, sound: Sound):
        macro = sound.macro if sound.macro.key else self._effective_global_macro()
        if macro.key:
            self.macro_engine.execute(
                macro,
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

    def _make_sound_callback(self, sound: Sound):
        if sound.shortcut_pass_through:
            shortcut = sound.shortcut

            def cb():
                self.play_sound(sound)
                _simulate_shortcut(shortcut)

            return cb
        return lambda: self.play_sound(sound)

    def find_shortcut_conflict(self, shortcut: str, exclude: str = "") -> Optional[str]:
        """Return a label of what already uses *shortcut*, or None if free."""
        if not shortcut or shortcut == exclude:
            return None
        for sound in self.config.sounds:
            if sound.shortcut == shortcut:
                return f"Sound: {sound.name}"
        for sc, label in [
            (self.config.channel_game_shortcut, "Toggle Game Mic"),
            (self.config.channel_chat_shortcut, "Toggle Chat Mic"),
            (self.config.stop_all_shortcut, "Stop All Sounds"),
            (self.config.loopback_shortcut, "Toggle Loopback"),
        ]:
            if sc == shortcut:
                return label
        return None

    def clear_shortcut(self, shortcut: str):
        """Remove *shortcut* from every place it is currently registered."""
        for sound in self.config.sounds:
            if sound.shortcut == shortcut:
                sound.shortcut = ""
        if self.config.channel_game_shortcut == shortcut:
            self.config.channel_game_shortcut = ""
        if self.config.channel_chat_shortcut == shortcut:
            self.config.channel_chat_shortcut = ""
        if self.config.stop_all_shortcut == shortcut:
            self.config.stop_all_shortcut = ""
        if self.config.loopback_shortcut == shortcut:
            self.config.loopback_shortcut = ""

    def reload_hotkeys(self):
        shortcuts = {}
        for sound in self.config.sounds:
            if sound.shortcut:
                shortcuts[sound.shortcut] = self._make_sound_callback(sound)
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
        enabled = not self.config.monitor_enabled
        self.config.monitor_enabled = enabled
        self.engine.set_monitor_enabled(enabled)
        self.config.save()
        if self.main_window:
            self.main_window.refresh_loopback_status()

    def toggle_chat_channel(self):
        enabled = not self.engine.is_chat_enabled()
        self.engine.set_chat_enabled(enabled)
        self.config.channel_chat_enabled = enabled
        self.config.save()
        if self.main_window:
            self.main_window.refresh_channel_status()

    def reload_game_detection(self):
        """Update the process detector with current profiles and start/stop it."""
        self.game_detector.stop()
        if self.config.game_detection_enabled and not self.config.manual_game_profile:
            self.game_detector.set_profiles(self.config.game_profiles)
            self.game_detector.start()
        self.apply_game_macro()

    def apply_game_macro(self):
        """Apply the correct game macro based on manual override or detection."""
        if self.config.manual_game_profile:
            for p in self.config.game_profiles:
                if p.name == self.config.manual_game_profile:
                    self._game_macro_active = p.macro
                    return
            self._game_macro_active = None
        elif self.game_detector.active_profile:
            self._game_macro_active = self.game_detector.active_profile.macro
        else:
            self._game_macro_active = None

    def _on_game_detected(self, profile: Optional[GameProfile]):
        """Called by ProcessDetector when the active game changes."""
        if profile:
            self._game_macro_active = profile.macro
            print(f"[GameDetector] Detected: {profile.name} → macro key '{profile.macro.key}'")
        else:
            self._game_macro_active = None
            print("[GameDetector] No matching game detected, using default global macro")
        if self.main_window:
            games_tab = getattr(self.main_window, "games_tab", None)
            if games_tab:
                games_tab._update_status()

    def on_quit(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        self.game_detector.stop()
        self.hotkey_manager.stop()
        self.engine.stop()
        self.audio_controller.disable_mic_passthrough()
        self.audio_controller.destroy_virtual_devices()
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
    return QIcon(resource_path("gsboard.png"))
