"""
Windows audio controller using sounddevice for playback.

Virtual mic routing on Windows requires external software such as VB-Cable
(https://vb-audio.com/Cable/).  If no compatible virtual cable is detected,
the game/chat channels are unavailable and only the monitor (real headset)
channel will work.

Mic passthrough is implemented in software: a background thread reads from
the real microphone and writes the same samples (scaled by the passthrough
volume) to each active VB-Cable sink.
"""

import contextlib
import io
import threading
from typing import List, Optional, Tuple

import numpy as np
import sounddevice as sd
import soundfile as sf

from gsboard.audio.backend import AudioController, PlayHandle
from gsboard.audio.capabilities import AudioCapabilities, ChannelInfo

# URLs users are pointed at when parts of the VB-Cable suite are missing.
VBCABLE_INSTALL_URL = "https://vb-audio.com/Cable/"
VBCABLE_B_PURCHASE_URL = (
    "https://shop.vb-audio.com/en/win-apps/12-vb-cable-ab.html#/30-donation_s-p1_i_m_a_fan"
)

# Name fragments used to auto-detect VB-Cable devices.
# The free VB-Cable installs "CABLE Input / CABLE Output".  The paid add-ons
# install "CABLE-A / CABLE-B" or "CABLE-C / CABLE-D" pairs.
_VBCABLE_HINT_PREFIXES = (
    "CABLE Input",
    "CABLE-A Input",
    "CABLE-B Input",
    "CABLE-C Input",
    "CABLE-D Input",
)


def _source_for_sink(sink_name: str) -> str:
    """Return the VB-Cable *Output* (source/mic) device name paired with an
    *Input* (sink) device, so the UI can tell users which mic to pick in
    their target app."""
    return sink_name.replace(" Input", " Output", 1)


# ------------------------------------------------------------------
# PlayHandle implementation for sounddevice output streams
# ------------------------------------------------------------------


class SounddeviceHandle(PlayHandle):
    """Handle for audio playing in a background thread via sounddevice."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._done_event = threading.Event()

    def _run(self, data: np.ndarray, samplerate: int, device, channels: int):
        block_size = 1024
        try:
            with sd.OutputStream(
                samplerate=samplerate,
                channels=channels,
                dtype="float32",
                device=device,
                blocksize=block_size,
            ) as stream:
                idx = 0
                while idx < len(data) and not self._stop_event.is_set():
                    chunk = data[idx : idx + block_size]
                    if len(chunk) < block_size:
                        pad = np.zeros((block_size - len(chunk), channels), dtype="float32")
                        chunk = np.concatenate([chunk, pad])
                    stream.write(chunk)
                    idx += block_size
        except Exception as e:
            print(f"[WindowsAudio] playback error: {e}")
        finally:
            self._done_event.set()

    def stop(self):
        self._stop_event.set()
        self._done_event.wait(timeout=2.0)

    def wait(self, timeout: Optional[float] = None):
        self._done_event.wait(timeout=timeout)


# ------------------------------------------------------------------
# Mic passthrough — software mic → virtual cable routing
# ------------------------------------------------------------------


class _MicPassthrough:
    """Background thread copying real-mic audio into one or more sinks.

    The thread opens an input stream on the user-chosen mic plus an output
    stream for every target VB-Cable sink, then loops: read a block, scale
    by the current volume, write the same block to each sink. Stopping the
    thread closes all streams and releases the mic so other apps can use it.
    """

    _BLOCKSIZE = 480  # 10ms at 48kHz — low enough for near-realtime chat
    _SAMPLERATE = 48000
    _SINK_CHANNELS = 2  # VB-Cable sinks are stereo

    def __init__(self, mic_device: str, sinks: List[str], volume: float):
        self._mic_device = mic_device
        self._sinks = [s for s in sinks if s]
        self._volume = volume
        self._volume_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def set_volume(self, volume: float):
        with self._volume_lock:
            self._volume = volume

    def start(self) -> bool:
        if not self._sinks:
            return False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="gsboard-mic-passthrough"
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self):
        try:
            mic_channels = _input_channel_count(self._mic_device)
            mic_idx = _resolve_device_index(self._mic_device, output=False)
            sink_ids = [_resolve_device_index(sink, output=True) or sink for sink in self._sinks]
            with contextlib.ExitStack() as stack:
                in_stream = stack.enter_context(
                    sd.InputStream(
                        device=mic_idx if mic_idx is not None else self._mic_device,
                        channels=mic_channels,
                        samplerate=self._SAMPLERATE,
                        blocksize=self._BLOCKSIZE,
                        dtype="float32",
                    )
                )
                out_streams = [
                    stack.enter_context(
                        sd.OutputStream(
                            device=sink_id,
                            channels=self._SINK_CHANNELS,
                            samplerate=self._SAMPLERATE,
                            blocksize=self._BLOCKSIZE,
                            dtype="float32",
                        )
                    )
                    for sink_id in sink_ids
                ]
                while not self._stop.is_set():
                    data, _overflow = in_stream.read(self._BLOCKSIZE)
                    with self._volume_lock:
                        vol = self._volume
                    if vol != 1.0:
                        data = data * vol
                    if mic_channels == 1 and self._SINK_CHANNELS == 2:
                        # Duplicate mono mic into both stereo channels.
                        data = np.repeat(data, 2, axis=1)
                    for out in out_streams:
                        out.write(data)
        except Exception as e:
            print(f"[WindowsAudio] mic passthrough stopped: {e}")


def _spawn_sounddevice(wav_bytes: bytes, device) -> Optional[SounddeviceHandle]:
    try:
        buf = io.BytesIO(wav_bytes)
        data, samplerate = sf.read(buf, dtype="float32", always_2d=True)
    except Exception as e:
        print(f"[WindowsAudio] failed to decode WAV: {e}")
        return None

    # sounddevice raises ValueError when the device name exists on more
    # than one Windows host API (e.g. DirectSound + WASAPI), which silently
    # kills the playback thread. Resolve to a WASAPI index up-front so
    # only one match is ever considered.
    if isinstance(device, str):
        resolved = _resolve_device_index(device, output=True)
        if resolved is not None:
            device = resolved

    channels = data.shape[1]
    handle = SounddeviceHandle()
    threading.Thread(
        target=handle._run,
        args=(data, samplerate, device, channels),
        daemon=True,
    ).start()
    return handle


# ------------------------------------------------------------------
# Windows AudioController
# ------------------------------------------------------------------


class WindowsAudioController(AudioController):
    """
    Audio controller for Windows.

    game_sink / chat_sink can be passed explicitly (device name strings as
    returned by sounddevice).  When omitted, VB-Cable devices are
    auto-detected by well-known name fragments.
    """

    def __init__(
        self,
        game_sink: Optional[str] = None,
        chat_sink: Optional[str] = None,
    ):
        available = _list_vbcable_sinks()
        # Prefer a caller-supplied sink when it's still present on the
        # system; otherwise fall back to the first detected cable (game)
        # and the next one (chat), if any. Enforce that the two channels
        # never point at the same cable — if the saved config or fallback
        # logic would collide, drop chat to the next unused cable (or None).
        self._game_sink = (
            game_sink if game_sink in available else (available[0] if available else None)
        )
        remaining = [c for c in available if c != self._game_sink]
        if chat_sink and chat_sink in remaining:
            self._chat_sink = chat_sink
        else:
            self._chat_sink = remaining[0] if remaining else None
        self._passthrough: Optional[_MicPassthrough] = None

    # ------------------------------------------------------------------
    # AudioController — capabilities
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> AudioCapabilities:
        cable_count = len(_list_vbcable_sinks())
        return AudioCapabilities(
            # Dual channels only possible when at least two VB-Cable devices
            # are installed (the free cable plus a paid add-on, or Potato).
            supports_dual_channels=cable_count >= 2,
            supports_mic_passthrough=True,
            supports_virtual_device_management=False,
            supports_user_device_selection=True,
            channels_hint_html=(
                "Sounds are routed through <b>VB-Cable</b>. "
                "Select the matching <b>CABLE … Output</b> as the "
                "microphone in your target app (game, OBS, etc.). "
                "A second channel requires a second cable "
                f"(<a href='{VBCABLE_B_PURCHASE_URL}'>VB-Cable A+B</a>) — "
                "most users only need the Game channel."
            ),
            setup_hint_html=(
                "Virtual mic routing on Windows is handled by "
                f"<a href='{VBCABLE_INSTALL_URL}'>VB-Cable</a> "
                "(free, installed separately). "
                "Install or uninstall it from Windows Settings."
            ),
            mic_passthrough_hint=None,
        )

    def list_channel_candidates(self) -> List[Tuple[str, str]]:
        return [(name, name) for name in _list_vbcable_sinks()]

    def set_channel_device(self, channel: str, device_id: Optional[str]) -> None:
        if channel == "game":
            self._game_sink = device_id or None
        elif channel == "chat":
            self._chat_sink = device_id or None
        else:
            raise ValueError(f"Unknown channel: {channel!r}")

    def get_channel_info(self, channel: str) -> ChannelInfo:
        if channel not in ("game", "chat"):
            raise ValueError(f"Unknown channel: {channel!r}")

        label = "Game" if channel == "game" else "Chat"
        sink_active = (
            self.is_game_sink_active() if channel == "game" else self.is_chat_sink_active()
        )
        src_active = (
            self.is_game_source_active() if channel == "game" else self.is_chat_source_active()
        )
        source_id = self.game_source_id if channel == "game" else self.chat_source_id

        cable_count = len(_list_vbcable_sinks())
        if cable_count == 0:
            missing_html = f"{label}: install <a href='{VBCABLE_INSTALL_URL}'>VB-Cable</a>"
        else:
            missing_html = (
                f"{label}: assign a device above, or add a second cable "
                f"(<a href='{VBCABLE_B_PURCHASE_URL}'>VB-Cable A+B, paid</a>)"
            )
        return self._channel_info_or_missing(
            label,
            sink_active,
            src_active,
            source_id,
            missing_html=missing_html,
            missing_short_state="n/a",
        )

    @staticmethod
    def _channel_info_or_missing(
        label: str,
        sink_active: bool,
        src_active: bool,
        source_id: Optional[str],
        missing_html: str,
        missing_short_state: str = "inactive",
    ) -> ChannelInfo:
        if sink_active and src_active:
            return ChannelInfo(
                label=label,
                active=True,
                device_name=source_id,
                short_state="active",
            )
        return ChannelInfo(
            label=label,
            active=False,
            unavailable_html=missing_html,
            short_state=missing_short_state,
        )

    # ------------------------------------------------------------------
    # AudioController — virtual device identifiers
    # ------------------------------------------------------------------

    @property
    def game_sink_id(self) -> Optional[str]:
        return self._game_sink

    @property
    def game_source_id(self) -> Optional[str]:
        return _source_for_sink(self._game_sink) if self._game_sink else None

    @property
    def chat_sink_id(self) -> Optional[str]:
        return self._chat_sink

    @property
    def chat_source_id(self) -> Optional[str]:
        return _source_for_sink(self._chat_sink) if self._chat_sink else None

    # ------------------------------------------------------------------
    # AudioController — virtual device lifecycle (no-op on Windows)
    # ------------------------------------------------------------------

    def create_virtual_devices(self) -> bool:
        """
        No-op — virtual audio cables must be installed separately on Windows.
        Returns True if at least one virtual cable device was detected.
        """
        return bool(self._game_sink or self._chat_sink)

    def destroy_virtual_devices(self):
        """No-op on Windows."""

    # ------------------------------------------------------------------
    # AudioController — status
    # ------------------------------------------------------------------

    def is_game_sink_active(self) -> bool:
        return _output_device_present(self._game_sink)

    def is_game_source_active(self) -> bool:
        # Assume the VB-Cable Output side is present when the Input side is.
        return self.is_game_sink_active()

    def is_chat_sink_active(self) -> bool:
        return _output_device_present(self._chat_sink)

    def is_chat_source_active(self) -> bool:
        return self.is_chat_sink_active()

    # ------------------------------------------------------------------
    # AudioController — device listing
    # ------------------------------------------------------------------

    def list_output_devices(self) -> List[Tuple[str, str]]:
        return _list_devices(output=True)

    def list_input_devices(self) -> List[Tuple[str, str]]:
        return _list_devices(output=False)

    # ------------------------------------------------------------------
    # AudioController — playback
    # ------------------------------------------------------------------

    def play_wav(self, wav_bytes: bytes, device_id: Optional[str]) -> Optional[PlayHandle]:
        return _spawn_sounddevice(wav_bytes, device_id)

    # ------------------------------------------------------------------
    # AudioController — mic passthrough (software-mixed into VB-Cables)
    # ------------------------------------------------------------------

    def enable_mic_passthrough(self, mic_device_id: str, volume: float) -> bool:
        if not mic_device_id:
            return False
        sinks = [s for s in (self._game_sink, self._chat_sink) if s]
        if not sinks:
            return False
        if self._passthrough is not None:
            self._passthrough.stop()
        self._passthrough = _MicPassthrough(mic_device_id, sinks, volume)
        return self._passthrough.start()

    def disable_mic_passthrough(self):
        if self._passthrough is not None:
            self._passthrough.stop()
            self._passthrough = None

    def set_mic_passthrough_volume(self, volume: float) -> None:
        if self._passthrough is not None:
            self._passthrough.set_volume(volume)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _preferred_hostapi_index() -> Optional[int]:
    """Pick a single Windows host API so each physical device appears once.

    Windows exposes every device through MME, DirectSound, WASAPI and
    (sometimes) WDM-KS. MME also truncates names to 31 characters, which
    would otherwise make the same cable look like two different devices.
    Prefer WASAPI (modern, never truncated); fall back to DirectSound,
    then MME, then whatever is default.
    """
    try:
        apis = sd.query_hostapis()
    except Exception:
        return None
    preference = ("Windows WASAPI", "Windows DirectSound", "MME")
    for wanted in preference:
        for idx, api in enumerate(apis):
            if api.get("name") == wanted:
                return idx
    return None


def _list_vbcable_sinks() -> List[str]:
    """Return the names of all detected VB-Cable *Input* devices.

    Only one host API is enumerated (see ``_preferred_hostapi_index``)
    so each physical cable is reported exactly once. Order is stable
    (dictated by ``sounddevice``'s enumeration) and usable as a fallback
    when the user has not picked a device.
    """
    seen: List[str] = []
    api_idx = _preferred_hostapi_index()
    try:
        for dev in sd.query_devices():
            if dev.get("max_output_channels", 0) <= 0:
                continue
            if api_idx is not None and dev.get("hostapi") != api_idx:
                continue
            name = dev.get("name", "")
            if not any(name.startswith(prefix) for prefix in _VBCABLE_HINT_PREFIXES):
                continue
            if name not in seen:
                seen.append(name)
    except Exception:
        pass
    return seen


def _list_devices(*, output: bool) -> List[Tuple[str, str]]:
    """Enumerate playback or capture devices on the preferred host API.

    Filtering to one host API avoids showing the same physical device
    once per Windows audio API (MME/DirectSound/WASAPI). Duplicate
    names across different drivers (rare) are also deduped.
    """
    channel_key = "max_output_channels" if output else "max_input_channels"
    api_idx = _preferred_hostapi_index()
    seen = set()
    results: List[Tuple[str, str]] = []
    try:
        for dev in sd.query_devices():
            if dev.get(channel_key, 0) <= 0:
                continue
            if api_idx is not None and dev.get("hostapi") != api_idx:
                continue
            name = dev.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            results.append((name, name))
    except Exception:
        pass
    return results


def _resolve_device_index(name: Optional[str], *, output: bool) -> Optional[int]:
    """Resolve a device *name* to an index on the preferred host API.

    sounddevice's built-in name-to-index lookup fails with ``ValueError``
    when the same name exists under multiple Windows host APIs (MME,
    DirectSound, WASAPI). Resolving against the preferred API up-front
    side-steps that and keeps streams on the modern API consistently.
    """
    if not name:
        return None
    api_idx = _preferred_hostapi_index()
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("name") != name:
                continue
            if api_idx is not None and dev.get("hostapi") != api_idx:
                continue
            if output and dev.get("max_output_channels", 0) <= 0:
                continue
            if not output and dev.get("max_input_channels", 0) <= 0:
                continue
            return idx
    except Exception:
        pass
    return None


def _input_channel_count(name: Optional[str]) -> int:
    """Return the max input channels for *name* (default 1 if not found)."""
    if not name:
        return 1
    idx = _resolve_device_index(name, output=False)
    if idx is None:
        return 1
    try:
        dev = sd.query_devices(idx)
        return max(1, min(2, int(dev.get("max_input_channels", 1))))
    except Exception:
        return 1


def _output_device_present(name: Optional[str]) -> bool:
    if not name:
        return False
    try:
        for dev in sd.query_devices():
            if dev.get("name") == name and dev.get("max_output_channels", 0) > 0:
                return True
    except Exception:
        pass
    return False
