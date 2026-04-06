"""X11 global hotkey backend using pynput."""

from typing import Callable, Dict

from .backend import HotkeyBackend

# X11 KP keysyms for numpad keys (used when NumLock is on)
_KP_KEYSYMS: Dict[str, int] = {
    "num_0": 0xffb0, "num_1": 0xffb1, "num_2": 0xffb2, "num_3": 0xffb3,
    "num_4": 0xffb4, "num_5": 0xffb5, "num_6": 0xffb6, "num_7": 0xffb7,
    "num_8": 0xffb8, "num_9": 0xffb9,
    "num_decimal":  0xffae, "num_add":      0xffab, "num_subtract": 0xffad,
    "num_multiply": 0xffaa, "num_divide":   0xffaf, "num_enter":    0xff8d,
}
# Range of keysym values considered "keypad" — 0xff80 … 0xffbf
_KP_VK_MIN = 0xff80
_KP_VK_MAX = 0xffbf


def _parse_shortcut(shortcut: str, keyboard_module) -> list:
    """Parse a pynput-style shortcut string.

    Handles ``<num_X>`` tokens (numpad keys) that pynput's own parser
    does not recognise, by converting them to ``KeyCode.from_vk(keysym)``.
    """
    from pynput.keyboard import KeyCode

    tokens = [t.strip() for t in shortcut.lower().split("+")]
    keys = []
    for token in tokens:
        bare = token.strip("<>")
        if bare in _KP_KEYSYMS:
            keys.append(KeyCode.from_vk(_KP_KEYSYMS[bare]))
        else:
            parsed = keyboard_module.HotKey.parse(token)
            keys.extend(parsed)
    return keys


def _normalize_key(key, listener) -> object:
    """Like ``listener.canonical(key)`` but preserves KP keysyms.

    ``canonical()`` strips modifier state and can collapse numpad digit
    keys (e.g. KP_5 → '5'), making them indistinguishable from the
    matching regular key.  We detect KP keysyms by their vk range and
    return a stable ``KeyCode.from_vk`` instead.
    """
    from pynput.keyboard import KeyCode

    vk = getattr(key, "vk", None)
    if vk is not None and _KP_VK_MIN <= vk <= _KP_VK_MAX:
        return KeyCode.from_vk(vk)
    return listener.canonical(key)


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
                keys = _parse_shortcut(shortcut, keyboard)
                hk = keyboard.HotKey(keys, cb)
                hotkey_map[shortcut] = hk
            except Exception as exc:
                print(f"[{self.name}] Invalid shortcut '{shortcut}': {exc}")

        if not hotkey_map:
            return False

        def on_press(key):
            normalized = _normalize_key(key, self._listener)
            for hk in hotkey_map.values():
                hk.press(normalized)

        def on_release(key):
            normalized = _normalize_key(key, self._listener)
            for hk in hotkey_map.values():
                hk.release(normalized)

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
