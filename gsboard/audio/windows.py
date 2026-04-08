"""
Windows audio controller using sounddevice for playback.

Virtual mic routing on Windows requires external software such as VB-Cable
(https://vb-audio.com/Cable/).  If no compatible virtual cable is detected,
the game/chat channels are unavailable and only the monitor (real headset)
channel will work.

Mic passthrough is not automatically configured — use VoiceMeeter or route
manually in the Windows sound settings.
"""

import io
import threading
from typing import List, Tuple, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

from gsboard.audio.backend import AudioController, PlayHandle

# Name fragments used to auto-detect VB-Cable devices
_VBCABLE_GAME_HINTS = ["CABLE Input", "VB-Audio Virtual Cable"]
_VBCABLE_CHAT_HINTS = ["CABLE Input B", "VB-Audio Cable B"]


# ------------------------------------------------------------------
# PlayHandle implementation for sounddevice output streams
# ------------------------------------------------------------------

class SounddeviceHandle(PlayHandle):
    """Handle for audio playing in a background thread via sounddevice."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._done_event = threading.Event()

    def _run(self, data: np.ndarray, samplerate: int,
             device, channels: int):
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
                    chunk = data[idx: idx + block_size]
                    if len(chunk) < block_size:
                        pad = np.zeros(
                            (block_size - len(chunk), channels), dtype="float32"
                        )
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


def _spawn_sounddevice(wav_bytes: bytes,
                       device) -> Optional[SounddeviceHandle]:
    try:
        buf = io.BytesIO(wav_bytes)
        data, samplerate = sf.read(buf, dtype="float32", always_2d=True)
    except Exception as e:
        print(f"[WindowsAudio] failed to decode WAV: {e}")
        return None

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
        self._game_sink = game_sink or _detect_output_device(_VBCABLE_GAME_HINTS)
        self._chat_sink = chat_sink or _detect_output_device(_VBCABLE_CHAT_HINTS)
        # The "source" seen by games is the VB-Cable Output side — we can't
        # enumerate it programmatically, so store a descriptive placeholder.
        self._game_source = "CABLE Output (VB-Audio Virtual Cable)"
        self._chat_source = "CABLE Output B (VB-Audio Cable B)"

    # ------------------------------------------------------------------
    # AudioController — virtual device identifiers
    # ------------------------------------------------------------------

    @property
    def game_sink_id(self) -> Optional[str]:
        return self._game_sink

    @property
    def game_source_id(self) -> Optional[str]:
        return self._game_source

    @property
    def chat_sink_id(self) -> Optional[str]:
        return self._chat_sink

    @property
    def chat_source_id(self) -> Optional[str]:
        return self._chat_source

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
        results = []
        try:
            for dev in sd.query_devices():
                if dev.get("max_output_channels", 0) > 0:
                    name = dev.get("name", "")
                    results.append((name, name))
        except Exception:
            pass
        return results

    def list_input_devices(self) -> List[Tuple[str, str]]:
        results = []
        try:
            for dev in sd.query_devices():
                if dev.get("max_input_channels", 0) > 0:
                    name = dev.get("name", "")
                    results.append((name, name))
        except Exception:
            pass
        return results

    # ------------------------------------------------------------------
    # AudioController — playback
    # ------------------------------------------------------------------

    def play_wav(self, wav_bytes: bytes,
                 device_id: Optional[str]) -> Optional[PlayHandle]:
        return _spawn_sounddevice(wav_bytes, device_id)

    # ------------------------------------------------------------------
    # AudioController — mic passthrough (not supported natively)
    # ------------------------------------------------------------------

    def enable_mic_passthrough(self, mic_device_id: str,
                               volume: float) -> bool:
        print(
            "[WindowsAudio] Mic passthrough is not automatically configured "
            "on Windows. Use VB-Cable + VoiceMeeter for manual routing."
        )
        return False

    def disable_mic_passthrough(self):
        pass


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _detect_output_device(hints: List[str]) -> Optional[str]:
    """Return the first output device whose name contains one of *hints*."""
    try:
        for dev in sd.query_devices():
            if dev.get("max_output_channels", 0) > 0:
                name = dev.get("name", "")
                for hint in hints:
                    if hint.lower() in name.lower():
                        return name
    except Exception:
        pass
    return None


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
