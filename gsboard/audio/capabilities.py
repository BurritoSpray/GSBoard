"""Backend capability descriptors.

UI code queries these instead of branching on ``sys.platform`` so that
platform-specific logic stays inside the audio backends.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChannelInfo:
    """Runtime state and UX hints for one virtual mic channel."""

    label: str
    """Human-readable name, e.g. ``"Game"`` or ``"Chat"``."""

    active: bool
    """True if the channel is usable right now."""

    device_name: Optional[str] = None
    """Current device name when ``active`` is True, else ``None``."""

    unavailable_html: Optional[str] = None
    """Rich-text explanation rendered when ``active`` is False.

    Use when the channel has a structural reason for being unavailable
    (e.g. missing paid add-on) rather than the user simply not running
    the backend. May contain ``<a href>`` tags.
    """

    short_state: str = "inactive"
    """One-word summary for compact displays such as the status bar."""


@dataclass(frozen=True)
class AudioCapabilities:
    """What the current audio backend can do."""

    supports_dual_channels: bool
    """True if independent game and chat virtual mics are possible."""

    supports_mic_passthrough: bool
    """True if the backend can route the real mic into virtual sinks."""

    supports_virtual_device_management: bool
    """True if ``create_virtual_devices`` / ``destroy_virtual_devices``
    do meaningful work. When False, UI should hide the controls rather
    than wire them to silent no-ops."""

    supports_user_device_selection: bool = False
    """True if the user picks which device backs each channel. When True,
    ``list_channel_candidates`` returns a non-empty list and the UI
    exposes dropdowns for the game and chat channels. When False the
    backend manages its own channel devices (e.g. PipeWire sinks)."""

    channels_hint_html: Optional[str] = None
    """Rich-text hint shown above the channel toggles explaining how
    sounds are routed on this backend."""

    setup_hint_html: Optional[str] = None
    """Rich-text hint describing what the user needs to install or
    configure for the backend to be fully functional."""

    mic_passthrough_hint: Optional[str] = None
    """Tooltip shown when the passthrough control is disabled."""
