import os
import threading
from typing import Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSlot


def _detect_session() -> str:
    xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    if xdg == "wayland" or wayland_display:
        return "wayland"
    return "x11"


SESSION_TYPE = _detect_session()

_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"
_REQUEST_IFACE = "org.freedesktop.portal.Request"
_SESSION_IFACE = "org.freedesktop.portal.Session"


class _PortalHotkeyManager(QObject):
    """
    Global hotkeys via xdg-desktop-portal GlobalShortcuts (Wayland).
    Requires KDE Plasma 5.27+ or GNOME 43+.
    """

    def __init__(self, shortcuts: Dict[str, Callable]):
        super().__init__()
        from PyQt6.QtDBus import QDBusConnection

        self._shortcuts_input = dict(shortcuts)
        self._callbacks: Dict[str, Callable] = {}   # portal_id → callback
        self._session_handle: Optional[str] = None
        self._bus = QDBusConnection.sessionBus()
        # sender name used to build request handle paths
        self._sender_name = (
            self._bus.baseService().lstrip(":").replace(".", "_")
        )
        self._token_seq = 0

    def _next_token(self) -> str:
        self._token_seq += 1
        return f"gsboard{self._token_seq}"

    def start(self) -> bool:
        from PyQt6.QtDBus import QDBusInterface

        if not self._bus.isConnected():
            return False

        iface = QDBusInterface(
            _PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE, self._bus
        )
        if not iface.isValid():
            print("[HotkeyManager] xdg-portal GlobalShortcuts not available")
            return False

        handle_token = self._next_token()
        session_token = self._next_token()
        request_path = (
            f"/org/freedesktop/portal/desktop/request/"
            f"{self._sender_name}/{handle_token}"
        )

        ok = self._bus.connect(
            _PORTAL_SERVICE, request_path, _REQUEST_IFACE,
            "Response", self._on_create_session_response,
        )
        if not ok:
            print("[HotkeyManager] Could not connect to portal Request signal")
            return False

        reply = iface.call(
            "CreateSession",
            {
                "handle_token": handle_token,
                "session_handle_token": session_token,
            },
        )
        from PyQt6.QtDBus import QDBusMessage
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            print(f"[HotkeyManager] CreateSession error: {reply.errorMessage()}")
            return False

        print("[HotkeyManager] Portal session requested, waiting for response...")
        return True

    @pyqtSlot(int, "QVariantMap")
    def _on_create_session_response(self, response: int, results: dict):
        from PyQt6.QtDBus import QDBusInterface

        if response != 0:
            print(f"[HotkeyManager] Portal CreateSession denied (response={response})")
            return

        self._session_handle = results.get("session_handle", "")
        if not self._session_handle:
            print("[HotkeyManager] Portal: missing session_handle in response")
            return

        print(f"[HotkeyManager] Portal session created: {self._session_handle}")

        # Connect to the Activated signal on the session object
        self._bus.connect(
            _PORTAL_SERVICE,
            self._session_handle,
            _PORTAL_IFACE,
            "Activated",
            self._on_activated,
        )

        # Build the shortcuts list: aa{sv}
        # Each entry is a dict with keys: id, description, preferred_trigger
        shortcuts_list = []
        for i, (shortcut_str, cb) in enumerate(self._shortcuts_input.items()):
            portal_id = f"gsboard_{i}"
            self._callbacks[portal_id] = cb
            trigger = _shortcut_to_portal_trigger(shortcut_str)
            shortcuts_list.append({
                "id": portal_id,
                "description": shortcut_str,
                "preferred_trigger": trigger,
            })

        handle_token = self._next_token()
        request_path = (
            f"/org/freedesktop/portal/desktop/request/"
            f"{self._sender_name}/{handle_token}"
        )
        self._bus.connect(
            _PORTAL_SERVICE, request_path, _REQUEST_IFACE,
            "Response", self._on_bind_response,
        )

        iface = QDBusInterface(
            _PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE, self._bus
        )
        reply = iface.call(
            "BindShortcuts",
            self._session_handle,
            shortcuts_list,
            "",  # parent_window
            {"handle_token": handle_token},
        )
        from PyQt6.QtDBus import QDBusMessage
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            print(f"[HotkeyManager] BindShortcuts error: {reply.errorMessage()}")

    @pyqtSlot(int, "QVariantMap")
    def _on_bind_response(self, response: int, results: dict):
        if response != 0:
            print(f"[HotkeyManager] Portal BindShortcuts denied (response={response})")
            return
        print(f"[HotkeyManager] Portal shortcuts bound: {list(self._callbacks.keys())}")

    @pyqtSlot(str, str, "qulonglong", "QVariantMap")
    def _on_activated(self, session_handle: str, shortcut_id: str,
                      timestamp: int, options: dict):
        cb = self._callbacks.get(shortcut_id)
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def stop(self):
        if self._session_handle:
            from PyQt6.QtDBus import QDBusInterface
            iface = QDBusInterface(
                _PORTAL_SERVICE, self._session_handle,
                _SESSION_IFACE, self._bus,
            )
            iface.call("Close")
            self._session_handle = None


class HotkeyManager:
    def __init__(self):
        self._callbacks: Dict[str, Callable] = {}
        self._listener = None
        self._running = False
        self._session = SESSION_TYPE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def register(self, shortcut: str, callback: Callable):
        with self._lock:
            self._callbacks[shortcut] = callback
        self._restart_listener()

    def set_shortcuts(self, shortcuts: Dict[str, Callable]):
        """Replace all shortcuts at once and restart the listener only once."""
        with self._lock:
            self._callbacks = dict(shortcuts)
        if self._running:
            self._restart_listener()

    def unregister(self, shortcut: str):
        with self._lock:
            self._callbacks.pop(shortcut, None)
        self._restart_listener()

    def clear(self):
        with self._lock:
            self._callbacks.clear()
        self._stop_listener()

    def start(self):
        self._running = True
        self._restart_listener()

    def stop(self):
        self._running = False
        self._stop_listener()

    def _restart_listener(self):
        self._stop_listener()
        if not self._running:
            return
        with self._lock:
            if not self._callbacks:
                return
            shortcuts = dict(self._callbacks)

        if self._session == "x11":
            self._start_x11(shortcuts)
        else:
            self._start_wayland(shortcuts)

    def _start_x11(self, shortcuts: Dict[str, Callable]):
        from pynput import keyboard

        hotkey_map = {}
        for shortcut, cb in shortcuts.items():
            try:
                hk = keyboard.HotKey(
                    keyboard.HotKey.parse(shortcut),
                    cb,
                )
                hotkey_map[shortcut] = hk
            except Exception as e:
                print(f"[HotkeyManager] Invalid shortcut '{shortcut}': {e}")

        if not hotkey_map:
            return

        def on_press(key):
            for hk in hotkey_map.values():
                hk.press(listener.canonical(key))

        def on_release(key):
            for hk in hotkey_map.values():
                hk.release(listener.canonical(key))

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        self._listener = listener

    def _start_wayland(self, shortcuts: Dict[str, Callable]):
        try:
            from PyQt6.QtDBus import QDBusConnection  # noqa: F401 — verify available
        except ImportError:
            print("[HotkeyManager] PyQt6.QtDBus not available, hotkeys disabled on Wayland")
            return

        mgr = _PortalHotkeyManager(shortcuts)
        if mgr.start():
            self._listener = mgr
        else:
            print("[HotkeyManager] Portal unavailable — hotkeys disabled on Wayland")

    def _stop_listener(self):
        self._stop_event.set()
        if self._listener is not None:
            try:
                if hasattr(self._listener, "stop"):
                    self._listener.stop()
            except Exception:
                pass
            self._listener = None


def _shortcut_to_portal_trigger(shortcut: str) -> str:
    """Convert <ctrl>+<f9> → CTRL+F9 for xdg-portal preferred_trigger."""
    parts = [p.strip().strip("<>").upper() for p in shortcut.split("+")]
    return "+".join(parts)
