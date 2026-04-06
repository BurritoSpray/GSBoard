"""
HotkeyManager — session-aware global shortcut manager.

Automatically selects the appropriate backend:
  - X11  → X11Backend  (pynput)
  - Wayland → WaylandBackend  (KGlobalAccel, then xdg-portal fallback)
"""

import os
import threading
from typing import Callable, Dict

from .backend import HotkeyBackend


def _detect_session() -> str:
    import sys
    if sys.platform == "win32":
        return "windows"
    xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if xdg == "wayland" or wayland_display:
        return "wayland"
    return "x11"


SESSION_TYPE = _detect_session()


def _make_backend() -> HotkeyBackend:
    if SESSION_TYPE == "windows":
        from .windows import WindowsBackend
        return WindowsBackend()
    if SESSION_TYPE == "wayland":
        from .wayland import WaylandBackend
        return WaylandBackend()
    from .x11 import X11Backend
    return X11Backend()


class HotkeyManager:
    """
    Session-aware global hotkey manager.

    Usage::

        mgr = HotkeyManager()
        mgr.start()
        mgr.set_shortcuts({"<ctrl>+<f9>": play_sound, "<ctrl>+<f10>": stop_all})
        # … later …
        mgr.stop()
    """

    def __init__(self):
        self._callbacks: Dict[str, Callable] = {}
        self._backend: HotkeyBackend = _make_backend()
        self._running = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, shortcut: str, callback: Callable):
        """Add or replace a single shortcut."""
        with self._lock:
            self._callbacks[shortcut] = callback
        self._apply()

    def unregister(self, shortcut: str):
        """Remove a single shortcut."""
        with self._lock:
            self._callbacks.pop(shortcut, None)
        self._apply()

    def set_shortcuts(self, shortcuts: Dict[str, Callable]):
        """Replace all shortcuts at once (single backend update)."""
        with self._lock:
            self._callbacks = dict(shortcuts)
        if self._running:
            self._apply()

    def clear(self):
        """Remove all shortcuts and stop the backend."""
        with self._lock:
            self._callbacks.clear()
        self._backend.stop()

    def suspend(self):
        """Temporarily stop listening without clearing shortcuts."""
        self._backend.stop()

    def resume(self):
        """Resume listening after a suspend (no-op if not started)."""
        if self._running:
            self._apply()

    def start(self):
        """Enable hotkey listening.  Call before or after set_shortcuts."""
        self._running = True
        self._apply()

    def stop(self):
        """Disable hotkey listening and release backend resources."""
        self._running = False
        self._backend.stop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply(self):
        """Push the current shortcut table to the backend."""
        if not self._running:
            return
        with self._lock:
            shortcuts = dict(self._callbacks)
        if not shortcuts:
            self._backend.stop()
            return
        self._backend.update(shortcuts)
