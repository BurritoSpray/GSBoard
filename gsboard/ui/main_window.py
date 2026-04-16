from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QStatusBar, QLabel, QWidget, QVBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from gsboard.ui.sound_grid import SoundGrid
from gsboard.ui.settings import SettingsPanel
from gsboard.ui.shortcut_editor import ShortcutEditor
from gsboard.ui.games_tab import GamesTab
from gsboard.ui.about_tab import AboutTab


class MainWindow(QMainWindow):
    def __init__(self, app_controller):
        super().__init__()
        self.app_controller = app_controller
        self.setWindowTitle("GSBoard")
        self.setMinimumSize(800, 550)
        self.resize(900, 600)

        self._build_ui()
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(3000)

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.sound_grid = SoundGrid(self.app_controller)
        self.settings_panel = SettingsPanel(self.app_controller)
        self.shortcut_editor = ShortcutEditor(self.app_controller)
        self.games_tab = GamesTab(self.app_controller)

        self.tabs.addTab(self.sound_grid, "Library")
        self.tabs.addTab(self.shortcut_editor, "Shortcuts")
        self.tabs.addTab(self.games_tab, "Games")
        self.tabs.addTab(self.settings_panel, "Settings")
        self.tabs.addTab(AboutTab(), "About")

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._mic_label = QLabel()
        self.status_bar.addPermanentWidget(self._mic_label)
        self._update_status()

    def _update_status(self):
        ac = self.app_controller.audio_controller
        engine = self.app_controller.engine
        game_info = ac.get_channel_info("game")
        chat_info = ac.get_channel_info("chat")
        game_ok = game_info.active
        chat_ok = chat_info.active

        game_state = (
            ("ON" if engine.is_game_enabled() else "muted")
            if game_ok else game_info.short_state.upper()
        )
        chat_state = (
            ("ON" if engine.is_chat_enabled() else "muted")
            if chat_ok else chat_info.short_state.upper()
        )
        loopback_state = "ON" if engine.is_monitor_enabled() else "OFF"

        # Active game detection
        game_profile = None
        detector = self.app_controller.game_detector
        config = self.app_controller.config
        if config.manual_game_profile:
            for p in config.game_profiles:
                if p.name == config.manual_game_profile:
                    game_profile = p
                    break
        elif detector.active_profile:
            game_profile = detector.active_profile

        if game_ok or chat_ok:
            parts = [
                f"Game mic: {game_state}",
                f"Chat mic: {chat_state}",
                f"Loopback: {loopback_state}",
            ]
            if game_profile:
                parts.append(f"Game: {game_profile.name}")
            self._mic_label.setText("  |  ".join(parts))
            self._mic_label.setStyleSheet("color: #4caf50;")
        else:
            self._mic_label.setText("Virtual mics inactive — go to Settings to create them")
            self._mic_label.setStyleSheet("color: #f44336;")

    def refresh_sounds(self):
        self.sound_grid.refresh()
        self.shortcut_editor.refresh()

    def refresh_channel_status(self):
        self.settings_panel.refresh_channel_status()

    def refresh_loopback_status(self):
        self._update_status()
        self.settings_panel.refresh_loopback_status()

    def closeEvent(self, event):
        if self.app_controller.config.minimize_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()
            self.app_controller.on_quit()
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()
