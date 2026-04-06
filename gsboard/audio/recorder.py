import threading
import wave
from pathlib import Path
from typing import Optional
import numpy as np
import sounddevice as sd


class AudioRecorder:
    SAMPLERATE = 48000
    CHANNELS = 1

    def __init__(self):
        self._recording = False
        self._frames = []
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def start(self, device_name: Optional[str] = None):
        if self._recording:
            return
        self._frames.clear()
        self._recording = True
        device_index = self._find_device(device_name) if device_name else None
        self._stream = sd.InputStream(
            samplerate=self.SAMPLERATE,
            channels=self.CHANNELS,
            dtype="float32",
            device=device_index,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self, output_path: str) -> bool:
        if not self._recording:
            return False
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            frames = list(self._frames)
        if not frames:
            return False

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        audio = np.concatenate(frames, axis=0)
        pcm = (audio * 32767).astype(np.int16)
        with wave.open(output_path, "w") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLERATE)
            wf.writeframes(pcm.tobytes())
        return True

    def is_recording(self) -> bool:
        return self._recording

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self._frames.append(indata.copy())

    def _find_device(self, name: str) -> Optional[int]:
        devices = sd.query_devices()
        for i, dev in enumerate(devices):
            if name in dev["name"] and dev["max_input_channels"] > 0:
                return i
        return None

    def list_input_devices(self) -> list:
        devices = sd.query_devices()
        return [
            {"index": i, "name": dev["name"]}
            for i, dev in enumerate(devices)
            if dev["max_input_channels"] > 0
        ]
