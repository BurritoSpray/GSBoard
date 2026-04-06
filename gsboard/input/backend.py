"""Abstract base class for global hotkey backends."""

from abc import ABC, abstractmethod
from typing import Callable, Dict


class HotkeyBackend(ABC):
    """Common interface for platform-specific hotkey implementations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name used in log messages."""
        ...

    @abstractmethod
    def start(self, shortcuts: Dict[str, Callable]) -> bool:
        """
        Register *shortcuts* and start listening.

        Parameters
        ----------
        shortcuts:
            Mapping of shortcut string (pynput format, e.g. ``<ctrl>+<f9>``)
            to callback.  The callback is invoked from an arbitrary thread.

        Returns
        -------
        bool
            ``True`` if the backend started successfully, ``False`` otherwise.
        """
        ...

    @abstractmethod
    def update(self, shortcuts: Dict[str, Callable]) -> bool:
        """
        Replace the active shortcut set without a full stop/start cycle when
        possible.  Backends that cannot update in-place fall back to
        ``stop()`` + ``start()``.

        Returns
        -------
        bool
            ``True`` on success.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Unregister all shortcuts and release resources."""
        ...
