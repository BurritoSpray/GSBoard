"""Wayland global hotkey backends: KGlobalAccel (KDE) and xdg-portal fallback."""

import threading
from typing import Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSlot

from .backend import HotkeyBackend

# ---------------------------------------------------------------------------
# KGlobalAccel constants
# ---------------------------------------------------------------------------
_KGA_SERVICE = "org.kde.kglobalaccel"
_KGA_PATH = "/kglobalaccel"
_KGA_IFACE = "org.kde.KGlobalAccel"
_KGA_COMPONENT_IFACE = "org.kde.kglobalaccel.Component"
_COMPONENT = "gsboard"

# ---------------------------------------------------------------------------
# xdg-desktop-portal GlobalShortcuts constants
# ---------------------------------------------------------------------------
_PORTAL_SERVICE = "org.freedesktop.portal.Desktop"
_PORTAL_PATH = "/org/freedesktop/portal/desktop"
_PORTAL_IFACE = "org.freedesktop.portal.GlobalShortcuts"
_REQUEST_IFACE = "org.freedesktop.portal.Request"
_SESSION_IFACE = "org.freedesktop.portal.Session"


# ---------------------------------------------------------------------------
# Key-code conversion helpers (pynput format → Qt key int)
# ---------------------------------------------------------------------------

def _build_key_map() -> Dict[str, int]:
    from PyQt6.QtCore import Qt

    key_map: Dict[str, int] = {}

    # Letters a-z
    for c in "abcdefghijklmnopqrstuvwxyz":
        qt_key = getattr(Qt.Key, f"Key_{c.upper()}", None)
        if qt_key is not None:
            key_map[c] = qt_key.value

    # Digits 0-9
    for d in range(10):
        qt_key = getattr(Qt.Key, f"Key_{d}", None)
        if qt_key is not None:
            key_map[str(d)] = qt_key.value

    # F-keys f1–f35
    for i in range(1, 36):
        qt_key = getattr(Qt.Key, f"Key_F{i}", None)
        if qt_key is not None:
            key_map[f"f{i}"] = qt_key.value

    # Common special keys
    specials = {
        "space": Qt.Key.Key_Space,
        "tab": Qt.Key.Key_Tab,
        "return": Qt.Key.Key_Return,
        "enter": Qt.Key.Key_Return,
        "escape": Qt.Key.Key_Escape,
        "esc": Qt.Key.Key_Escape,
        "backspace": Qt.Key.Key_Backspace,
        "delete": Qt.Key.Key_Delete,
        "insert": Qt.Key.Key_Insert,
        "home": Qt.Key.Key_Home,
        "end": Qt.Key.Key_End,
        "page_up": Qt.Key.Key_PageUp,
        "page_down": Qt.Key.Key_PageDown,
        "up": Qt.Key.Key_Up,
        "down": Qt.Key.Key_Down,
        "left": Qt.Key.Key_Left,
        "right": Qt.Key.Key_Right,
        "print_screen": Qt.Key.Key_Print,
        "scroll_lock": Qt.Key.Key_ScrollLock,
        "pause": Qt.Key.Key_Pause,
        "caps_lock": Qt.Key.Key_CapsLock,
        "num_lock": Qt.Key.Key_NumLock,
    }
    for name, qt_key in specials.items():
        key_map[name] = qt_key.value

    return key_map


_KEY_MAP: Optional[Dict[str, int]] = None


def _shortcut_to_qt_keycode(shortcut: str) -> Optional[int]:
    """
    Convert a pynput-style shortcut string to a Qt key code integer for
    KGlobalAccel.

    Example: ``"<ctrl>+<f9>"`` → ``0x04000000 | Qt.Key.Key_F9.value``
    Returns ``None`` when the shortcut cannot be mapped.
    """
    global _KEY_MAP
    if _KEY_MAP is None:
        _KEY_MAP = _build_key_map()

    from PyQt6.QtCore import Qt

    modifier_flags = {
        "ctrl": Qt.KeyboardModifier.ControlModifier.value,
        "control": Qt.KeyboardModifier.ControlModifier.value,
        "alt": Qt.KeyboardModifier.AltModifier.value,
        "shift": Qt.KeyboardModifier.ShiftModifier.value,
        "super": Qt.KeyboardModifier.MetaModifier.value,
        "meta": Qt.KeyboardModifier.MetaModifier.value,
        "cmd": Qt.KeyboardModifier.MetaModifier.value,
        "win": Qt.KeyboardModifier.MetaModifier.value,
    }

    modifiers = 0
    key_code: Optional[int] = None

    for part in shortcut.lower().split("+"):
        token = part.strip().strip("<>").strip()
        if token in modifier_flags:
            modifiers |= modifier_flags[token]
        elif token in _KEY_MAP:
            key_code = _KEY_MAP[token]
        else:
            print(f"[wayland] Unknown key token '{token}' in shortcut '{shortcut}'")
            return None

    if key_code is None:
        return None
    return modifiers | key_code


def _shortcut_to_portal_trigger(shortcut: str) -> str:
    """Convert ``<ctrl>+<f9>`` → ``CTRL+F9`` for xdg-portal preferred_trigger."""
    parts = [p.strip().strip("<>").upper() for p in shortcut.split("+")]
    return "+".join(parts)


# ---------------------------------------------------------------------------
# KGlobalAccel backend
# ---------------------------------------------------------------------------

class _KGlobalAccelManager(QObject):
    """
    Registers global shortcuts via the KDE KGlobalAccel DBus service.
    Works on KDE Plasma 5/6 Wayland and X11 sessions.
    """

    def __init__(self, shortcuts: Dict[str, Callable]):
        super().__init__()
        from PyQt6.QtDBus import QDBusConnection

        self._shortcuts_input = dict(shortcuts)
        self._callbacks: Dict[str, Callable] = {}   # action_unique_name → callback
        self._bus = QDBusConnection.sessionBus()
        self._registered: list[str] = []            # action unique names we registered
        self._component_path: Optional[str] = None

    def start(self) -> bool:
        from PyQt6.QtDBus import QDBusConnection

        if not self._bus.isConnected():
            return False

        # Use dbus-python for method calls: PyQt6 marshals Python lists as
        # QVariantList (av) but KGlobalAccel expects QStringList (as) / QList<int> (ai).
        try:
            import dbus as _dbus
        except ImportError:
            print("[KGlobalAccel] dbus-python not available (install python-dbus)")
            return False

        try:
            session_bus = _dbus.SessionBus()
            kga_obj = session_bus.get_object(_KGA_SERVICE, _KGA_PATH)
            kga_iface = _dbus.Interface(kga_obj, _KGA_IFACE)
        except _dbus.DBusException as e:
            print(f"[KGlobalAccel] Service not available: {e}")
            return False

        registered_any = False
        for i, (shortcut, cb) in enumerate(self._shortcuts_input.items()):
            key_code = _shortcut_to_qt_keycode(shortcut)
            if key_code is None:
                print(f"[KGlobalAccel] Cannot convert shortcut '{shortcut}', skipping")
                continue

            action_name = f"action_{i}"
            action_id = _dbus.Array([_COMPONENT, action_name, "GSBoard", shortcut], signature="s")

            # Step 1: register the action
            try:
                kga_iface.doRegister(action_id)
            except _dbus.DBusException as e:
                print(f"[KGlobalAccel] doRegister failed for '{shortcut}': {e}")
                continue

            # Step 2: assign the key — setShortcut(QStringList, QList<int>, uint)
            # SetPresent = 2
            try:
                kga_iface.setShortcut(
                    action_id,
                    _dbus.Array([key_code], signature="i"),
                    _dbus.UInt32(2),
                )
            except _dbus.DBusException as e:
                print(f"[KGlobalAccel] setShortcut failed for '{shortcut}': {e}")
                try:
                    kga_iface.unregister(_COMPONENT, action_name)
                except _dbus.DBusException:
                    pass
                continue

            self._callbacks[action_name] = cb
            self._registered.append(action_name)
            registered_any = True

        if not registered_any:
            return False

        # Get the component's actual DBus object path
        try:
            component_path = str(kga_iface.getComponent(_COMPONENT))
        except _dbus.DBusException as e:
            print(f"[KGlobalAccel] getComponent failed: {e}")
            self._cleanup_registrations(kga_iface)
            return False

        self._component_path = component_path

        # Use PyQt6 for signal subscription — it integrates with Qt's event loop
        connected = self._bus.connect(
            _KGA_SERVICE,
            self._component_path,
            _KGA_COMPONENT_IFACE,
            "globalShortcutPressed",
            self._on_shortcut_pressed,
        )
        if not connected:
            print("[KGlobalAccel] Could not connect to globalShortcutPressed signal")
            self._cleanup_registrations(kga_iface)
            return False

        self._kga_iface = kga_iface  # keep reference for cleanup
        print(f"[KGlobalAccel] Registered {len(self._registered)} shortcut(s) "
              f"at {self._component_path}")
        return True

    @pyqtSlot(str, str, "qlonglong")
    def _on_shortcut_pressed(self, component_unique: str, shortcut_unique: str, timestamp: int):
        cb = self._callbacks.get(shortcut_unique)
        if cb:
            threading.Thread(target=cb, daemon=True).start()

    def stop(self):
        if self._component_path:
            self._bus.disconnect(
                _KGA_SERVICE,
                self._component_path,
                _KGA_COMPONENT_IFACE,
                "globalShortcutPressed",
                self._on_shortcut_pressed,
            )
            self._component_path = None

        kga_iface = getattr(self, "_kga_iface", None)
        if kga_iface is not None:
            self._cleanup_registrations(kga_iface)
            self._kga_iface = None

    def _cleanup_registrations(self, kga_iface):
        import dbus as _dbus
        for action_name in self._registered:
            try:
                kga_iface.unregister(_COMPONENT, action_name)
            except _dbus.DBusException:
                pass
        self._registered.clear()
        self._callbacks.clear()


class KGlobalAccelBackend(HotkeyBackend):
    """Wayland/KDE backend using org.kde.kglobalaccel via DBus."""

    @property
    def name(self) -> str:
        return "KGlobalAccel"

    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        try:
            from PyQt6.QtDBus import QDBusConnection  # noqa: F401
        except ImportError:
            print(f"[{self.name}] PyQt6.QtDBus not available")
            return False

        self._manager = _KGlobalAccelManager(shortcuts)
        if self._manager.start():
            return True
        self._manager = None
        return False

    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        self.stop()
        return self.start(shortcuts)

    def stop(self) -> None:
        mgr = getattr(self, "_manager", None)
        if mgr is not None:
            mgr.stop()
            self._manager = None


# ---------------------------------------------------------------------------
# xdg-desktop-portal GlobalShortcuts backend
# ---------------------------------------------------------------------------

class _PortalManager(QObject):
    """
    Global shortcuts via xdg-desktop-portal GlobalShortcuts protocol.
    Requires KDE Plasma 5.27+ or GNOME 43+.
    """

    def __init__(self, shortcuts: Dict[str, Callable]):
        super().__init__()
        from PyQt6.QtDBus import QDBusConnection

        self._shortcuts_input = dict(shortcuts)
        self._callbacks: Dict[str, Callable] = {}
        self._session_handle: Optional[str] = None
        self._bus = QDBusConnection.sessionBus()
        self._sender_name = (
            self._bus.baseService().lstrip(":").replace(".", "_")
        )
        self._token_seq = 0

    def _next_token(self) -> str:
        self._token_seq += 1
        return f"gsboard{self._token_seq}"

    def start(self) -> bool:
        from PyQt6.QtDBus import QDBusInterface, QDBusMessage

        if not self._bus.isConnected():
            return False

        iface = QDBusInterface(
            _PORTAL_SERVICE, _PORTAL_PATH, _PORTAL_IFACE, self._bus
        )
        if not iface.isValid():
            print("[Portal] GlobalShortcuts portal not available")
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
            print("[Portal] Could not connect to Request signal")
            return False

        reply = iface.call(
            "CreateSession",
            {"handle_token": handle_token, "session_handle_token": session_token},
        )
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            print(f"[Portal] CreateSession error: {reply.errorMessage()}")
            return False

        print("[Portal] Session requested, waiting for response...")
        return True

    @pyqtSlot(int, "QVariantMap")
    def _on_create_session_response(self, response: int, results: dict):
        from PyQt6.QtDBus import QDBusInterface, QDBusMessage

        if response != 0:
            print(f"[Portal] CreateSession denied (response={response})")
            return

        self._session_handle = results.get("session_handle", "")
        if not self._session_handle:
            print("[Portal] Missing session_handle in response")
            return

        print(f"[Portal] Session created: {self._session_handle}")

        self._bus.connect(
            _PORTAL_SERVICE, self._session_handle, _PORTAL_IFACE,
            "Activated", self._on_activated,
        )

        shortcuts_list = []
        for i, (shortcut_str, cb) in enumerate(self._shortcuts_input.items()):
            portal_id = f"gsboard_{i}"
            self._callbacks[portal_id] = cb
            shortcuts_list.append({
                "id": portal_id,
                "description": shortcut_str,
                "preferred_trigger": _shortcut_to_portal_trigger(shortcut_str),
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
            "",
            {"handle_token": handle_token},
        )
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            print(f"[Portal] BindShortcuts error: {reply.errorMessage()}")

    @pyqtSlot(int, "QVariantMap")
    def _on_bind_response(self, response: int, results: dict):
        if response != 0:
            print(f"[Portal] BindShortcuts denied (response={response})")
            return
        print(f"[Portal] Shortcuts bound: {list(self._callbacks.keys())}")

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
                _PORTAL_SERVICE, self._session_handle, _SESSION_IFACE, self._bus,
            )
            iface.call("Close")
            self._session_handle = None


class PortalBackend(HotkeyBackend):
    """Wayland backend using xdg-desktop-portal GlobalShortcuts."""

    @property
    def name(self) -> str:
        return "xdg-portal"

    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        try:
            from PyQt6.QtDBus import QDBusConnection  # noqa: F401
        except ImportError:
            print(f"[{self.name}] PyQt6.QtDBus not available")
            return False

        self._manager = _PortalManager(shortcuts)
        if self._manager.start():
            return True
        self._manager = None
        return False

    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        self.stop()
        return self.start(shortcuts)

    def stop(self) -> None:
        mgr = getattr(self, "_manager", None)
        if mgr is not None:
            mgr.stop()
            self._manager = None


# ---------------------------------------------------------------------------
# Composite Wayland backend: KGlobalAccel → portal
# ---------------------------------------------------------------------------

class WaylandBackend(HotkeyBackend):
    """
    Wayland hotkey backend.

    Tries KGlobalAccel (KDE) first, then falls back to xdg-desktop-portal.
    """

    @property
    def name(self) -> str:
        active = getattr(self, "_active", None)
        return f"Wayland({active.name if active else 'none'})"

    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        for BackendCls in (KGlobalAccelBackend, PortalBackend):
            backend = BackendCls()
            if backend.start(shortcuts):
                self._active: Optional[HotkeyBackend] = backend
                print(f"[WaylandBackend] Using {backend.name}")
                return True
            print(f"[WaylandBackend] {backend.name} unavailable, trying next...")

        print("[WaylandBackend] All Wayland backends failed — hotkeys disabled")
        self._active = None
        return False

    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        active = getattr(self, "_active", None)
        if active is not None:
            return active.update(shortcuts)
        return self.start(shortcuts)

    def stop(self) -> None:
        active = getattr(self, "_active", None)
        if active is not None:
            active.stop()
            self._active = None
