"""Abstract base classes for platform-specific audio controllers."""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional

from gsboard.audio.capabilities import AudioCapabilities, ChannelInfo


class PlayHandle(ABC):
    """Opaque handle for a single audio stream playing on one device."""

    @abstractmethod
    def stop(self):
        """Stop playback immediately."""
        ...

    @abstractmethod
    def wait(self, timeout: Optional[float] = None):
        """Block until playback finishes naturally (or timeout elapses)."""
        ...


class AudioController(ABC):
    """
    Platform-specific audio routing controller.

    Implementations
    ---------------
    Linux / PipeWire  →  PipeWireController  (gsboard/audio/pipewire.py)
    Windows           →  WindowsAudioController  (gsboard/audio/windows.py)
    """

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def capabilities(self) -> AudioCapabilities:
        """What this backend can do in principle (driver-level support)."""
        ...

    @abstractmethod
    def get_channel_info(self, channel: str) -> ChannelInfo:
        """Return the runtime status and UX hints for one channel.

        ``channel`` is ``"game"`` or ``"chat"``.
        """
        ...

    # ------------------------------------------------------------------
    # Channel → device mapping (user-configurable backends only)
    # ------------------------------------------------------------------

    def list_channel_candidates(self) -> List[Tuple[str, str]]:
        """Return ``(device_id, display_name)`` pairs that can back a channel.

        Default: empty list — backends that manage their own virtual
        devices (e.g. PipeWire) don't expose a selection. Backends that
        rely on pre-existing external virtual cables (e.g. VB-Cable on
        Windows) override this to list detected cables.
        """
        return []

    def set_channel_device(self, channel: str, device_id: Optional[str]) -> None:
        """Assign a device to a channel (``"game"`` or ``"chat"``).

        Default: no-op. Only backends that return a non-empty list from
        ``list_channel_candidates`` need to honour this.
        """

    # ------------------------------------------------------------------
    # Virtual device identifiers
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def game_sink_id(self) -> Optional[str]:
        """Output device ID for the game audio channel."""
        ...

    @property
    @abstractmethod
    def game_source_id(self) -> Optional[str]:
        """Input device ID / name for the game virtual mic."""
        ...

    @property
    @abstractmethod
    def chat_sink_id(self) -> Optional[str]:
        """Output device ID for the chat audio channel."""
        ...

    @property
    @abstractmethod
    def chat_source_id(self) -> Optional[str]:
        """Input device ID / name for the chat virtual mic."""
        ...

    # ------------------------------------------------------------------
    # Virtual device lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def create_virtual_devices(self) -> bool:
        """Create virtual audio devices. Returns True on success."""
        ...

    @abstractmethod
    def destroy_virtual_devices(self):
        """Remove virtual audio devices."""
        ...

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @abstractmethod
    def is_game_sink_active(self) -> bool: ...

    @abstractmethod
    def is_game_source_active(self) -> bool: ...

    @abstractmethod
    def is_chat_sink_active(self) -> bool: ...

    @abstractmethod
    def is_chat_source_active(self) -> bool: ...

    def get_virtual_mic_name(self) -> Optional[str]:
        """Return the game virtual mic source name if active, else None."""
        return self.game_source_id if self.is_game_source_active() else None

    # ------------------------------------------------------------------
    # Device listing
    # ------------------------------------------------------------------

    @abstractmethod
    def list_output_devices(self) -> List[Tuple[str, str]]:
        """Return list of (id, description) for available output devices."""
        ...

    @abstractmethod
    def list_input_devices(self) -> List[Tuple[str, str]]:
        """Return list of (id, description) for available input devices."""
        ...

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    @abstractmethod
    def play_wav(self, wav_bytes: bytes,
                 device_id: Optional[str]) -> Optional[PlayHandle]:
        """
        Start playing WAV data on the given device asynchronously.

        Returns a PlayHandle for stopping / waiting, or None if the
        backend could not start playback.
        """
        ...

    # ------------------------------------------------------------------
    # Mic passthrough
    # ------------------------------------------------------------------

    @abstractmethod
    def enable_mic_passthrough(self, mic_device_id: str,
                               volume: float) -> bool:
        """Route mic input into both virtual sinks. Returns True on success."""
        ...

    @abstractmethod
    def disable_mic_passthrough(self):
        """Stop all mic passthrough routing."""
        ...

    def set_mic_passthrough_volume(self, volume: float) -> None:
        """Update a running passthrough's volume without restarting it.

        Default: no-op — backends without cheap live volume should leave
        the slider's debounced save-and-reapply to pick up the change.
        """
