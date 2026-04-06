import json
import os
from pathlib import Path
from typing import List, Optional

from gsboard.models.sound import Sound


CONFIG_DIR = Path.home() / ".config" / "gsboard"
CONFIG_FILE = CONFIG_DIR / "config.json"


class AppConfig:
    def __init__(self):
        self.sounds_folder: str = str(Path.home() / "Documents" / "git" / "GSBoard" / "sounds")
        self.sounds: List[Sound] = []
        self.output_device: Optional[str] = None
        self.mic_device: Optional[str] = None
        self.mic_passthrough: bool = False
        self.mic_passthrough_volume: float = 1.0
        self.master_volume: float = 1.0
        self.virtual_sink_name: str = "gsboard_sink"
        # Two output channels
        self.channel_game_enabled: bool = True
        self.channel_chat_enabled: bool = True
        self.channel_game_shortcut: str = ""
        self.channel_chat_shortcut: str = ""
        self.stop_all_shortcut: str = ""
        self.loopback_shortcut: str = ""
        self.minimize_to_tray: bool = True

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "sounds_folder": self.sounds_folder,
            "sounds": [s.to_dict() for s in self.sounds],
            "output_device": self.output_device,
            "mic_device": self.mic_device,
            "mic_passthrough": self.mic_passthrough,
            "mic_passthrough_volume": self.mic_passthrough_volume,
            "master_volume": self.master_volume,
            "virtual_sink_name": self.virtual_sink_name,
            "channel_game_enabled": self.channel_game_enabled,
            "channel_chat_enabled": self.channel_chat_enabled,
            "channel_game_shortcut": self.channel_game_shortcut,
            "channel_chat_shortcut": self.channel_chat_shortcut,
            "stop_all_shortcut": self.stop_all_shortcut,
            "loopback_shortcut": self.loopback_shortcut,
            "minimize_to_tray": self.minimize_to_tray,
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load(self):
        if not CONFIG_FILE.exists():
            return
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        self.sounds_folder = data.get("sounds_folder", self.sounds_folder)
        self.sounds = [Sound.from_dict(s) for s in data.get("sounds", [])]
        self.output_device = data.get("output_device")
        self.mic_device = data.get("mic_device")
        self.mic_passthrough = data.get("mic_passthrough", False)
        self.mic_passthrough_volume = data.get("mic_passthrough_volume", 1.0)
        self.master_volume = data.get("master_volume", 1.0)
        self.virtual_sink_name = data.get("virtual_sink_name", "gsboard_sink")
        self.channel_game_enabled = data.get("channel_game_enabled", True)
        self.channel_chat_enabled = data.get("channel_chat_enabled", True)
        self.channel_game_shortcut = data.get("channel_game_shortcut", "")
        self.channel_chat_shortcut = data.get("channel_chat_shortcut", "")
        self.stop_all_shortcut = data.get("stop_all_shortcut", "")
        self.loopback_shortcut = data.get("loopback_shortcut", "")
        self.minimize_to_tray = data.get("minimize_to_tray", True)
