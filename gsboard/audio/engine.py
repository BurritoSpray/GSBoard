"""
Audio engine using paplay subprocesses for PipeWire-native routing.

Each sound spawns a paplay process per enabled channel.  paplay speaks
PulseAudio protocol (via pipewire-pulse) and can target specific sinks by
name, which ALSA-backed sounddevice cannot do.  PipeWire mixes concurrent
paplay streams server-side, giving us free simultaneous playback.
"""

import io
import threading
from math import gcd
from typing import Dict, List, Optional, Callable
import subprocess

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from gsboard.audio.pipewire import PipeWireController

_SAMPLERATE = 48000
_CHANNELS = 2


def _to_wav_bytes(data: np.ndarray) -> bytes:
    """Encode a float32 stereo numpy array as a 32-bit float WAV in memory."""
    buf = io.BytesIO()
    # soundfile writes IEEE_FLOAT WAV which paplay handles natively
    sf.write(buf, data, _SAMPLERATE, format="WAV", subtype="FLOAT")
    return buf.getvalue()


class PlayingSound:
    """Tracks running paplay subprocesses for one triggered sound."""

    def __init__(self, sound_id: str):
        self.sound_id = sound_id
        self.finished = threading.Event()
        self._procs: List[subprocess.Popen] = []
        self._lock = threading.Lock()

    def _monitor(self, cleanup_cb=None):
        for proc in list(self._procs):
            try:
                proc.wait()
            except Exception:
                pass
        self.finished.set()
        if cleanup_cb:
            cleanup_cb()

    def stop(self):
        with self._lock:
            procs = list(self._procs)
            self._procs.clear()
        for proc in procs:
            try:
                proc.kill()
            except Exception:
                pass
        self.finished.set()


class AudioEngine:
    def __init__(self, pipewire: PipeWireController):
        self.pipewire = pipewire
        self._master_volume: float = 1.0
        self._game_enabled: bool = True
        self._chat_enabled: bool = True

        # sound_id → PlayingSound for each channel
        self._game_playing: Dict[str, PlayingSound] = {}
        self._chat_playing: Dict[str, PlayingSound] = {}
        self._lock = threading.Lock()

        # Monitor output — the real headset so the user hears their own sounds
        self._monitor_device: Optional[str] = None
        self._monitor_playing: Dict[str, PlayingSound] = {}

        # Cache: file_path → wav bytes (at _SAMPLERATE, stereo, normalised)
        self._wav_cache: Dict[str, bytes] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self, game_device: Optional[str] = None,
              chat_device: Optional[str] = None) -> bool:
        # Nothing to start — streams are created on demand per sound.
        # Validate that paplay is available.
        try:
            subprocess.run(["paplay", "--version"],
                           capture_output=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            print("[AudioEngine] paplay not found — install pulseaudio-utils")
            return False

    def stop(self):
        self.stop_all()

    # ------------------------------------------------------------------ #
    # Volume / channel control                                             #
    # ------------------------------------------------------------------ #

    def set_monitor_device(self, device: Optional[str]):
        """Set the real output device (headset) where sounds are also played locally.
        Pass None to use the PipeWire default output."""
        self._monitor_device = device

    def set_master_volume(self, volume: float):
        self._master_volume = max(0.0, min(1.0, volume))
        # Invalidate WAV cache so new plays use the updated volume
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
             volume: float = 1.0) -> Optional["PlayingSound"]:
        wav = self._load_wav(file_path, volume)
        if wav is None:
            return None

        ps = PlayingSound(sound_id)

        channels = []
        if self._game_enabled:
            channels.append((self.pipewire.sink_name, self._game_playing))
        if self._chat_enabled:
            channels.append((self.pipewire.chat_sink_name, self._chat_playing))
        # Always play to the real headset so the user hears the sound locally
        channels.append((self._monitor_device, self._monitor_playing))

        if not channels:
            ps.finished.set()
            return ps

        for sink, playing_dict in channels:
            # Stop previous instance of this sound on this channel
            with self._lock:
                old = playing_dict.pop(sound_id, None)
            if old:
                old.stop()

            proc = self._spawn_paplay(sink, wav)
            if proc:
                with self._lock:
                    ps._procs.append(proc)
                    playing_dict[sound_id] = ps

        if not ps._procs:
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
        for playing_dict in (self._game_playing, self._chat_playing, self._monitor_playing):
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
            ps = self._game_playing.get(sound_id) or self._chat_playing.get(sound_id)
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

    def _spawn_paplay(self, sink_name: Optional[str],
                      wav_bytes: bytes) -> Optional[subprocess.Popen]:
        try:
            cmd = ["paplay"]
            if sink_name:
                cmd.append(f"--device={sink_name}")
            cmd.append("/dev/stdin")
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            # Feed data then close stdin in a background thread so we don't block
            def _feed(p, data, label):
                try:
                    p.stdin.write(data)
                    p.stdin.close()
                except Exception:
                    pass
                try:
                    ret = p.wait(timeout=10)
                    if ret != 0:
                        err = p.stderr.read().decode(errors="replace").strip()
                        print(f"[AudioEngine] paplay({label}) exited {ret}: {err}")
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass
            label = sink_name or "default"
            threading.Thread(target=_feed, args=(proc, wav_bytes, label),
                             daemon=True).start()
            return proc
        except FileNotFoundError:
            print("[AudioEngine] paplay not found — install pulseaudio-utils or pipewire-pulse")
            return None
        except Exception as e:
            print(f"[AudioEngine] spawn failed: {e}")
            return None

    def _load_wav(self, file_path: str, volume: float) -> Optional[bytes]:
        # Cache key includes volume so different volumes don't alias
        cache_key = f"{file_path}:{volume:.4f}:{self._master_volume:.4f}"
        if cache_key in self._wav_cache:
            return self._wav_cache[cache_key]
        try:
            data, sr = sf.read(file_path, dtype="float32", always_2d=True)
        except Exception as e:
            print(f"[AudioEngine] Failed to load {file_path}: {e}")
            return None

        # Ensure stereo
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]

        # Resample if needed
        if sr != _SAMPLERATE:
            data = self._resample(data, sr, _SAMPLERATE)

        # Apply volume
        data = (data * volume * self._master_volume).clip(-1.0, 1.0)

        wav_bytes = _to_wav_bytes(data)
        self._wav_cache[cache_key] = wav_bytes
        return wav_bytes

    def _resample(self, data: np.ndarray, orig_sr: int,
                  target_sr: int) -> np.ndarray:
        g = gcd(orig_sr, target_sr)
        up, down = target_sr // g, orig_sr // g
        # resample_poly applies anti-aliasing filter — much better than linear interp
        resampled = resample_poly(data, up, down, axis=0)
        return resampled.astype("float32")

    def list_output_devices(self) -> list:
        """Returns PipeWire sinks visible via pactl."""
        return [(n, d) for n, d in self.pipewire.list_sinks()]
