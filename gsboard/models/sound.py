from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MacroConfig:
    key: str = ""
    pre_delay_ms: int = 0
    post_delay_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "pre_delay_ms": self.pre_delay_ms,
            "post_delay_ms": self.post_delay_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MacroConfig":
        return cls(
            key=d.get("key", ""),
            pre_delay_ms=d.get("pre_delay_ms", 0),
            post_delay_ms=d.get("post_delay_ms", 0),
        )


@dataclass
class Sound:
    name: str
    file_path: str
    color: str = "#4a90d9"
    volume: float = 1.0
    shortcut: str = ""
    shortcut_pass_through: bool = False
    macro: MacroConfig = field(default_factory=MacroConfig)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "color": self.color,
            "volume": self.volume,
            "shortcut": self.shortcut,
            "shortcut_pass_through": self.shortcut_pass_through,
            "macro": self.macro.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Sound":
        return cls(
            name=d.get("name", ""),
            file_path=d.get("file_path", ""),
            color=d.get("color", "#4a90d9"),
            volume=d.get("volume", 1.0),
            shortcut=d.get("shortcut", ""),
            shortcut_pass_through=d.get("shortcut_pass_through", False),
            macro=MacroConfig.from_dict(d.get("macro", {})),
        )
