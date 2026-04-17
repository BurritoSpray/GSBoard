import os
import sys
import subprocess
import threading
from typing import Callable, List, Optional

from gsboard.models.game_profile import GameProfile


class ProcessDetector:
    """Periodically polls running processes and fires a callback when a
    matching game profile is detected (or when no profile matches anymore)."""

    def __init__(self, interval: float = 3.0):
        self._interval = interval
        self._profiles: List[GameProfile] = []
        self._on_change: Optional[Callable[[Optional[GameProfile]], None]] = None
        self._active_profile: Optional[GameProfile] = None
        self._running = False
        self._timer: Optional[threading.Timer] = None

    def set_profiles(self, profiles: List[GameProfile]):
        self._profiles = list(profiles)

    def set_callback(self, cb: Callable[[Optional[GameProfile]], None]):
        self._on_change = cb

    def start(self):
        self._running = True
        self._schedule()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule(self):
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self):
        if not self._running:
            return
        try:
            self._check()
        except Exception as e:
            print(f"[ProcessDetector] error: {e}")
        self._schedule()

    def _check(self):
        running = _get_running_process_names()
        matched: Optional[GameProfile] = None
        for profile in self._profiles:
            if not profile.enabled:
                continue
            if profile.process_name.lower() in running:
                matched = profile
                break

        if matched is not self._active_profile:
            self._active_profile = matched
            if self._on_change:
                self._on_change(matched)

    @property
    def active_profile(self) -> Optional[GameProfile]:
        return self._active_profile


def _get_running_process_names() -> set:
    """Return a set of lowercase process names currently running."""
    if sys.platform == "win32":
        return _get_processes_windows()
    return _get_processes_linux()


def _get_processes_linux() -> set:
    names = set()
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            # Kernel comm name (e.g. "bash", "wine-preloader")
            try:
                with open(f"/proc/{entry}/comm", "r") as f:
                    names.add(f.read().strip().lower())
            except (OSError, PermissionError):
                pass
            # Full cmdline — needed for Wine/Proton games where the
            # .exe name only appears in the command-line arguments.
            try:
                with open(f"/proc/{entry}/cmdline", "rb") as f:
                    raw = f.read()
                if raw:
                    for arg in raw.split(b"\x00"):
                        arg_s = arg.decode("utf-8", errors="replace").strip().lower()
                        if not arg_s:
                            continue
                        # Extract basename from paths like
                        # "Z:\\path\\to\\PioneerGame.exe" or "/path/to/game"
                        base = arg_s.replace("\\", "/").rsplit("/", 1)[-1]
                        if base:
                            names.add(base)
            except (OSError, PermissionError):
                pass
    except OSError:
        pass
    return names


def _get_processes_windows() -> set:
    names = set()
    # CREATE_NO_WINDOW (0x08000000) suppresses the console flash when the
    # parent is a windowed (pythonw / --noconsole) build.
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False,
            creationflags=0x08000000,
        )
        for line in result.stdout.splitlines():
            parts = line.strip().strip('"').split('","')
            if parts:
                names.add(parts[0].lower())
    except FileNotFoundError:
        pass
    return names

if __name__ == "__main__":
    gp = GameProfile(name="test", process_name="PioneerGame.exe", enabled=True)
    pd = ProcessDetector()
    pd.set_profiles([gp])
    pd.start()
    pd._timer.join()