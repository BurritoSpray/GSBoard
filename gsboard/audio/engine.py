"""
Audio engine — platform-agnostic playback coordinator.

Each sound is played per-channel by delegating to the AudioController's
play_wav() method, which handles the platform-specific mechanics
(paplay on Linux/PipeWire, sounddevice on Windows).
"""

import threading
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from gsboard.audio.backend import AudioController, PlayHandle

_SAMPLERATE = 48000
_CHANNELS = 2


def _to_wav_bytes(data: np.ndarray) -> bytes:
    """Encode a float32 stereo numpy array as a 32-bit float WAV in memory."""
    import io
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, data, _SAMPLERATE, format="WAV", subtype="FLOAT")
    return buf.getvalue()


class PlayingSound:
    """Tracks running play handles for one triggered sound across all channels."""

    def __init__(self, sound_id: str):
        self.sound_id = sound_id
        self.finished = threading.Event()
        self._handles: List[PlayHandle] = []
        self._lock = threading.Lock()

    def _monitor(self, cleanup_cb=None):
        for handle in list(self._handles):
            try:
                handle.wait()
            except Exception:
                pass
        self.finished.set()
        if cleanup_cb:
            cleanup_cb()

    def stop(self):
        with self._lock:
            handles = list(self._handles)
            self._handles.clear()
        for handle in handles:
            try:
                handle.stop()
            except Exception:
                pass
        self.finished.set()


class AudioEngine:
    def __init__(self, controller: AudioController):
        self.controller = controller
        self._master_volume: float = 1.0
        self._game_enabled: bool = True
        self._chat_enabled: bool = True

        # sound_id → PlayingSound for each channel
        self._game_playing: Dict[str, PlayingSound] = {}
        self._chat_playing: Dict[str, PlayingSound] = {}
        self._lock = threading.Lock()

        # Monitor output — the real headset so the user hears their own sounds
        self._monitor_device: Optional[str] = None
        self._monitor_enabled: bool = True
        self._monitor_playing: Dict[str, PlayingSound] = {}

        # Test mode — bypass all channel settings, play only to the headset
        self._test_mode: bool = False

        # Cache: cache_key → wav bytes (at _SAMPLERATE, stereo, normalised)
        self._wav_cache: Dict[str, bytes] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self, game_device: Optional[str] = None,
              chat_device: Optional[str] = None) -> bool:
        # Streams are created on demand; nothing to initialise here.
        return True

    def stop(self):
        self.stop_all()

    # ------------------------------------------------------------------ #
    # Volume / channel control                                             #
    # ------------------------------------------------------------------ #

    def set_monitor_device(self, device: Optional[str]):
        """Set the real output device (headset) where sounds are also played locally."""
        self._monitor_device = device

    def set_monitor_enabled(self, enabled: bool):
        self._monitor_enabled = enabled
        if not enabled:
            self._stop_channel(self._monitor_playing)

    def is_monitor_enabled(self) -> bool:
        return self._monitor_enabled

    def set_test_mode(self, enabled: bool):
        self._test_mode = enabled

    def is_test_mode(self) -> bool:
        return self._test_mode

    def set_master_volume(self, volume: float):
        self._master_volume = max(0.0, min(1.0, volume))
        self._wav_cache.clear()

    def set_game_enabled(self, enabled: bool):
        self._game_enabled = enabled
        if not enabled:
            self._stop_channel(self._game_playing)

    def set_chat_enabled(self, enabled: bool):
        self._chat_enabled = enabled
        if not enabled:
            self._stop_channel(self._chat_playing)

    def is_game_enabled(self) -> bool:
        return self._game_enabled

    def is_chat_enabled(self) -> bool:
        return self._chat_enabled

    # ------------------------------------------------------------------ #
    # Playback                                                             #
    # ------------------------------------------------------------------ #

    def play(self, sound_id: str, file_path: str,
             volume: float = 1.0) -> Optional[PlayingSound]:
        wav = self._load_wav(file_path, volume)
        if wav is None:
            return None

        ps = PlayingSound(sound_id)

        if self._test_mode:
            channels = [(self._monitor_device, self._monitor_playing)]
        else:
            channels = []
            if self._game_enabled:
                channels.append((self.controller.game_sink_id, self._game_playing))
            if self._chat_enabled:
                channels.append((self.controller.chat_sink_id, self._chat_playing))
            if self._monitor_enabled:
                channels.append((self._monitor_device, self._monitor_playing))

        # Drop channels whose device didn't resolve. sounddevice treats a
        # None device as "system default output" and would leak audio into
        # the user's headset via a silently-unassigned game/chat channel.
        channels = [c for c in channels if c[0]]

        if not channels:
            ps.finished.set()
            return ps

        for device_id, playing_dict in channels:
            with self._lock:
                old = playing_dict.pop(sound_id, None)
            if old:
                old.stop()

            handle = self.controller.play_wav(wav, device_id)
            if handle:
                with self._lock:
                    ps._handles.append(handle)
                    playing_dict[sound_id] = ps

        if not ps._handles:
            ps.finished.set()
            return ps

        def _cleanup():
            with self._lock:
                for d in (self._game_playing, self._chat_playing,
                          self._monitor_playing):
                    if d.get(sound_id) is ps:
                        d.pop(sound_id, None)

        threading.Thread(
            target=ps._monitor, args=(_cleanup,), daemon=True
        ).start()
        return ps

    def stop_sound(self, sound_id: str):
        for playing_dict in (self._game_playing, self._chat_playing,
                              self._monitor_playing):
            with self._lock:
                ps = playing_dict.pop(sound_id, None)
            if ps:
                ps.stop()

    def stop_all(self):
        self._stop_channel(self._game_playing)
        self._stop_channel(self._chat_playing)
        self._stop_channel(self._monitor_playing)

    def is_playing(self, sound_id: str) -> bool:
        with self._lock:
            ps = (self._game_playing.get(sound_id) or
                  self._chat_playing.get(sound_id) or
                  self._monitor_playing.get(sound_id))
        return ps is not None and not ps.finished.is_set()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _stop_channel(self, playing_dict: Dict[str, PlayingSound]):
        with self._lock:
            items = list(playing_dict.values())
            playing_dict.clear()
        for ps in items:
            ps.stop()

    def _load_wav(self, file_path: str, volume: float) -> Optional[bytes]:
        cache_key = f"{file_path}:{volume:.4f}:{self._master_volume:.4f}"
        if cache_key in self._wav_cache:
            return self._wav_cache[cache_key]
        try:
            data, sr = sf.read(file_path, dtype="float32", always_2d=True)
        except Exception as e:
            print(f"[AudioEngine] Failed to load {file_path}: {e}")
            return None

        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]

        if sr != _SAMPLERATE:
            data = self._resample(data, sr, _SAMPLERATE)

        data = (data * volume * self._master_volume).clip(-1.0, 1.0)

        wav_bytes = _to_wav_bytes(data)
        self._wav_cache[cache_key] = wav_bytes
        return wav_bytes

    def _resample(self, data: np.ndarray, orig_sr: int,
                  target_sr: int) -> np.ndarray:
        # Linear interpolation — adequate for soundboard effects and avoids a
        # ~70 MB scipy dependency. Artifacts are only audible on pitch-sensitive
        # source material, which this app doesn't target.
        n_old = data.shape[0]
        if n_old < 2 or orig_sr == target_sr:
            return data.astype("float32", copy=False)
        n_new = max(1, int(round(n_old * target_sr / orig_sr)))
        src_idx = np.linspace(0.0, n_old - 1, n_new, dtype=np.float32)
        i0 = np.floor(src_idx).astype(np.int64)
        i1 = np.minimum(i0 + 1, n_old - 1)
        frac = (src_idx - i0).reshape(-1, 1)
        resampled = data[i0] * (1.0 - frac) + data[i1] * frac
        return resampled.astype("float32", copy=False)

    def list_output_devices(self) -> list:
        """Returns output devices from the active audio controller."""
        return [(n, d) for n, d in self.controller.list_output_devices()]
