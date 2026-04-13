from dataclasses import dataclass, field

from gsboard.models.sound import MacroConfig


@dataclass
class GameProfile:
    name: str = ""
    process_name: str = ""
    macro: MacroConfig = field(default_factory=MacroConfig)
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "process_name": self.process_name,
            "macro": self.macro.to_dict(),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GameProfile":
        return cls(
            name=d.get("name", ""),
            process_name=d.get("process_name", ""),
            macro=MacroConfig.from_dict(d.get("macro", {})),
            enabled=d.get("enabled", True),
        )
