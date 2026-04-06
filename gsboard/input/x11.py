"""X11 global hotkey backend using pynput."""

from typing import Callable, Dict

from .backend import HotkeyBackend


class X11Backend(HotkeyBackend):
    """Global hotkeys on X11 sessions via pynput."""

    @property
    def name(self) -> str:
        return "X11/pynput"

    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        from pynput import keyboard

        hotkey_map: Dict[str, object] = {}
        for shortcut, cb in shortcuts.items():
            try:
                hk = keyboard.HotKey(keyboard.HotKey.parse(shortcut), cb)
                hotkey_map[shortcut] = hk
            except Exception as exc:
                print(f"[{self.name}] Invalid shortcut '{shortcut}': {exc}")

        if not hotkey_map:
            return False

        def on_press(key):
            for hk in hotkey_map.values():
                hk.press(self._listener.canonical(key))

        def on_release(key):
            for hk in hotkey_map.values():
                hk.release(self._listener.canonical(key))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()
        return True

    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        self.stop()
        return self.start(shortcuts)

    def stop(self) -> None:
        listener = getattr(self, "_listener", None)
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
            self._listener = None
