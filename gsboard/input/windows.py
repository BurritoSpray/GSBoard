"""Windows global hotkey backend using Win32 RegisterHotKey via ctypes."""

import ctypes
import ctypes.wintypes
import threading
from typing import Callable, Dict, Optional, Tuple

from .backend import HotkeyBackend

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------
_WM_HOTKEY = 0x0312
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000  # suppress auto-repeat events

_user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


# ---------------------------------------------------------------------------
# Shortcut conversion: pynput format → (win32_modifiers, vk_code)
# ---------------------------------------------------------------------------


def _build_vk_map() -> Dict[str, int]:
    vk: Dict[str, int] = {}

    # Letters
    for c in "abcdefghijklmnopqrstuvwxyz":
        vk[c] = ord(c.upper())

    # Digits
    for d in range(10):
        vk[str(d)] = ord(str(d))

    # F-keys F1–F24  (VK_F1 = 0x70)
    for i in range(1, 25):
        vk[f"f{i}"] = 0x6F + i

    # Navigation / editing
    vk.update(
        {
            "backspace": 0x08,
            "tab": 0x09,
            "return": 0x0D,
            "enter": 0x0D,
            "escape": 0x1B,
            "esc": 0x1B,
            "space": 0x20,
            "page_up": 0x21,
            "page_down": 0x22,
            "end": 0x23,
            "home": 0x24,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "print_screen": 0x2C,
            "insert": 0x2D,
            "delete": 0x2E,
            # Numpad — token names match what shortcut_editor.py emits.
            "num0": 0x60,
            "num1": 0x61,
            "num2": 0x62,
            "num3": 0x63,
            "num4": 0x64,
            "num5": 0x65,
            "num6": 0x66,
            "num7": 0x67,
            "num8": 0x68,
            "num9": 0x69,
            "num_multiply": 0x6A,
            "num_add": 0x6B,
            "num_subtract": 0x6D,
            "num_decimal": 0x6E,
            "num_divide": 0x6F,
            # Win32 has no dedicated VK for Numpad Enter — it shares VK_RETURN
            # and is distinguished only by the extended scancode flag, which
            # RegisterHotKey ignores. Map to VK_RETURN for parity.
            "num_enter": 0x0D,
            # Misc
            "scroll_lock": 0x91,
            "pause": 0x13,
            "caps_lock": 0x14,
            "num_lock": 0x90,
            # OEM punctuation (US layout). RegisterHotKey keys by VK, so these
            # hold for any layout that shares the VK — users on non-US layouts
            # may see the physical US-position key trigger instead.
            ";": 0xBA,
            ":": 0xBA,
            "=": 0xBB,
            "+": 0xBB,
            ",": 0xBC,
            "<": 0xBC,
            "-": 0xBD,
            "_": 0xBD,
            ".": 0xBE,
            ">": 0xBE,
            "/": 0xBF,
            "?": 0xBF,
            "`": 0xC0,
            "~": 0xC0,
            "[": 0xDB,
            "{": 0xDB,
            "\\": 0xDC,
            "|": 0xDC,
            "]": 0xDD,
            "}": 0xDD,
            "'": 0xDE,
            '"': 0xDE,
        }
    )
    return vk


_VK_MAP: Optional[Dict[str, int]] = None


def _parse_shortcut(shortcut: str) -> Optional[Tuple[int, int]]:
    """
    Convert a pynput-style shortcut string to ``(win32_modifiers, vk_code)``.

    Examples::

        "<ctrl>+<f9>"          → (MOD_CONTROL | MOD_NOREPEAT, VK_F9)
        "<ctrl>+<shift>+a"     → (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord('A'))
        "<alt>+<super>+<left>" → (MOD_ALT | MOD_WIN | MOD_NOREPEAT, VK_LEFT)

    Returns ``None`` when the shortcut cannot be mapped.
    """
    global _VK_MAP
    if _VK_MAP is None:
        _VK_MAP = _build_vk_map()

    modifier_map = {
        "ctrl": _MOD_CONTROL,
        "control": _MOD_CONTROL,
        "alt": _MOD_ALT,
        "shift": _MOD_SHIFT,
        "super": _MOD_WIN,
        "meta": _MOD_WIN,
        "cmd": _MOD_WIN,
        "win": _MOD_WIN,
    }

    mods = _MOD_NOREPEAT
    vk: Optional[int] = None

    tokens = _tokenize_shortcut(shortcut)
    if tokens is None:
        print(f"[Windows] Malformed shortcut '{shortcut}'")
        return None

    for token in tokens:
        if token in modifier_map:
            mods |= modifier_map[token]
        elif token in _VK_MAP:
            vk = _VK_MAP[token]
        else:
            print(f"[Windows] Unknown key token '{token}' in shortcut '{shortcut}'")
            return None

    if vk is None:
        print(f"[Windows] No key found in shortcut '{shortcut}'")
        return None

    return mods, vk


def _tokenize_shortcut(shortcut: str) -> Optional[list]:
    """Split a pynput-style shortcut into tokens without confusing the "+"
    separator with a literal "+" key (e.g. ``<ctrl>++`` is Ctrl+Plus)."""
    s = shortcut.lower()
    tokens: list = []
    i, n = 0, len(s)
    while i < n:
        if s[i] == "<":
            j = s.find(">", i)
            if j < 0:
                return None
            tokens.append(s[i + 1 : j].strip())
            i = j + 1
            if i < n and s[i] == "+":
                i += 1  # separator after a wrapped modifier/key
        elif s[i] == "+":
            tokens.append("+")  # literal "+" key — prior char was a separator
            i += 1
        else:
            j = s.find("+", i)
            if j < 0:
                tokens.append(s[i:].strip())
                break
            tokens.append(s[i:j].strip())
            i = j + 1
    return [t for t in tokens if t]


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class WindowsBackend(HotkeyBackend):
    """
    Global hotkey backend for Windows using ``RegisterHotKey`` / ``UnregisterHotKey``
    (Win32 API via ctypes).  No additional dependencies required.

    A background thread runs a Win32 message loop to receive ``WM_HOTKEY``
    messages.  All callbacks are dispatched from that thread.
    """

    @property
    def name(self) -> str:
        return "Windows/RegisterHotKey"

    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        if _user32 is None:
            print(f"[{self.name}] ctypes.windll not available (not running on Windows)")
            return False

        self._id_to_cb: Dict[int, Callable] = {}
        self._id_to_shortcut: Dict[int, str] = {}
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._register_count = 0
        self._pending_shortcuts = dict(shortcuts)

        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="gsboard-hotkeys"
        )
        self._thread.start()
        # Wait for the thread to finish RegisterHotKey calls before returning,
        # so callers see an accurate success/failure result.
        self._ready_event.wait(timeout=5.0)
        return self._register_count > 0

    def _thread_main(self):
        # RegisterHotKey posts WM_HOTKEY to the calling thread's queue, and
        # UnregisterHotKey must be called from that same thread — so both the
        # registration and the message loop live here.
        for hk_id, (shortcut, cb) in enumerate(self._pending_shortcuts.items(), start=1):
            parsed = _parse_shortcut(shortcut)
            if parsed is None:
                continue
            mods, vk = parsed
            if _user32.RegisterHotKey(None, hk_id, mods, vk):
                self._id_to_cb[hk_id] = cb
                self._id_to_shortcut[hk_id] = shortcut
                self._register_count += 1
            else:
                err = ctypes.get_last_error()
                print(
                    f"[{self.name}] RegisterHotKey failed for '{shortcut}' "
                    f"(mods=0x{mods:04x}, vk=0x{vk:02x}, error={err})"
                )

        self._ready_event.set()

        if self._register_count == 0:
            return

        print(f"[{self.name}] Registered {self._register_count} shortcut(s)")
        try:
            self._message_loop()
        finally:
            for hk_id in list(self._id_to_cb.keys()):
                _user32.UnregisterHotKey(None, hk_id)

    def _message_loop(self):
        msg = ctypes.wintypes.MSG()
        while not self._stop_event.is_set():
            result = _user32.PeekMessageW(
                ctypes.byref(msg),
                None,
                _WM_HOTKEY,
                _WM_HOTKEY,
                1,  # PM_REMOVE
            )
            if result:
                hk_id = msg.wParam
                cb = self._id_to_cb.get(hk_id)
                if cb:
                    threading.Thread(target=cb, daemon=True).start()
            else:
                self._stop_event.wait(timeout=0.05)

    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        self.stop()
        return self.start(shortcuts)

    def stop(self) -> None:
        stop_event = getattr(self, "_stop_event", None)
        if stop_event is not None:
            stop_event.set()

        thread = getattr(self, "_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

        self._id_to_cb = {}
        self._id_to_shortcut = {}
        self._thread = None
