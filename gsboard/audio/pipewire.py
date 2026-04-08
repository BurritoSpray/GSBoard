import subprocess
import threading
from typing import Optional, List, Tuple

from gsboard.audio.backend import AudioController, PlayHandle


# ------------------------------------------------------------------
# PlayHandle implementation for paplay subprocesses
# ------------------------------------------------------------------

class PaplayHandle(PlayHandle):
    def __init__(self, proc: subprocess.Popen):
        self._proc = proc

    def stop(self):
        try:
            self._proc.kill()
        except Exception:
            pass

    def wait(self, timeout: Optional[float] = None):
        try:
            self._proc.wait(timeout=timeout)
        except Exception:
            pass


# ------------------------------------------------------------------
# PipeWire / PulseAudio controller
# ------------------------------------------------------------------

class PipeWireController(AudioController):
    def __init__(self, sink_name: str = "gsboard_sink"):
        # Game channel — for in-game audio (e.g. Arc Raiders)
        self.sink_name = sink_name
        self.source_name = f"{sink_name}_mic"
        # Chat channel — for voice apps (e.g. Discord)
        self.chat_sink_name = "gsboard_chat"
        self.chat_source_name = "gsboard_chat_mic"

        self._sink_module_id: Optional[str] = None
        self._source_module_id: Optional[str] = None
        self._chat_sink_module_id: Optional[str] = None
        self._chat_source_module_id: Optional[str] = None
        self._loopback_module_ids: List[str] = []

    # ------------------------------------------------------------------
    # AudioController — virtual device identifiers
    # ------------------------------------------------------------------

    @property
    def game_sink_id(self) -> Optional[str]:
        return self.sink_name

    @property
    def game_source_id(self) -> Optional[str]:
        return self.source_name

    @property
    def chat_sink_id(self) -> Optional[str]:
        return self.chat_sink_name

    @property
    def chat_source_id(self) -> Optional[str]:
        return self.chat_source_name

    # ------------------------------------------------------------------
    # AudioController — virtual device lifecycle
    # ------------------------------------------------------------------

    def create_virtual_devices(self) -> bool:
        return self.create_virtual_sink()

    def destroy_virtual_devices(self):
        self.destroy_virtual_sink()

    # ------------------------------------------------------------------
    # AudioController — status
    # ------------------------------------------------------------------

    def is_game_sink_active(self) -> bool:
        return self._is_active(self.sink_name, "sinks")

    def is_game_source_active(self) -> bool:
        return self._is_active(self.source_name, "sources")

    def is_chat_sink_active(self) -> bool:
        return self._is_active(self.chat_sink_name, "sinks")

    def is_chat_source_active(self) -> bool:
        return self._is_active(self.chat_source_name, "sources")

    # ------------------------------------------------------------------
    # AudioController — device listing
    # ------------------------------------------------------------------

    def list_output_devices(self) -> List[Tuple[str, str]]:
        return self.list_sinks()

    def list_input_devices(self) -> List[Tuple[str, str]]:
        return self.list_sources()

    # ------------------------------------------------------------------
    # AudioController — playback
    # ------------------------------------------------------------------

    def play_wav(self, wav_bytes: bytes,
                 device_id: Optional[str]) -> Optional[PaplayHandle]:
        """Spawn a paplay subprocess and feed it the WAV bytes."""
        try:
            cmd = ["paplay"]
            if device_id:
                cmd.append(f"--device={device_id}")
            cmd.append("/dev/stdin")
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                    stderr=subprocess.PIPE)

            label = device_id or "default"

            def _feed(p, data):
                try:
                    p.stdin.write(data)
                    p.stdin.close()
                except Exception:
                    pass
                try:
                    ret = p.wait(timeout=10)
                    if ret != 0:
                        err = p.stderr.read().decode(errors="replace").strip()
                        print(f"[PipeWire] paplay({label}) exited {ret}: {err}")
                except subprocess.TimeoutExpired:
                    pass
                except Exception:
                    pass

            threading.Thread(target=_feed, args=(proc, wav_bytes),
                             daemon=True).start()
            return PaplayHandle(proc)
        except FileNotFoundError:
            print("[PipeWire] paplay not found — install pulseaudio-utils or pipewire-pulse")
            return None
        except Exception as e:
            print(f"[PipeWire] spawn failed: {e}")
            return None

    # ------------------------------------------------------------------
    # AudioController — mic passthrough
    # ------------------------------------------------------------------

    def enable_mic_passthrough(self, mic_device_id: str,
                               volume: float) -> bool:
        return self._enable_mic_passthrough_impl(mic_device_id, volume)

    def disable_mic_passthrough(self):
        self._disable_mic_passthrough_impl()

    # ------------------------------------------------------------------
    # Virtual device lifecycle (internal)
    # ------------------------------------------------------------------

    def create_virtual_sink(self) -> bool:
        game_ok = self._create_channel(
            self.sink_name, self.source_name,
            "GSBoard Game Mic",
            "_sink_module_id", "_source_module_id",
        )
        chat_ok = self._create_channel(
            self.chat_sink_name, self.chat_source_name,
            "GSBoard Chat Mic",
            "_chat_sink_module_id", "_chat_source_module_id",
        )
        return game_ok and chat_ok

    def _create_channel(
        self,
        sink_name: str,
        source_name: str,
        display_name: str,
        sink_attr: str,
        source_attr: str,
    ) -> bool:
        if self._is_active(sink_name, "sinks"):
            return True
        try:
            r = subprocess.run(
                [
                    "pactl", "load-module", "module-null-sink",
                    f"sink_name={sink_name}",
                    f"sink_properties=device.description={sink_name}",
                    "channel_map=stereo",
                ],
                capture_output=True, text=True, check=True, timeout=10,
            )
            setattr(self, sink_attr, r.stdout.strip())

            r2 = subprocess.run(
                [
                    "pactl", "load-module", "module-remap-source",
                    f"source_name={source_name}",
                    f"master={sink_name}.monitor",
                ],
                capture_output=True, text=True, check=True, timeout=10,
            )
            setattr(self, source_attr, r2.stdout.strip())

            subprocess.run(
                ["pactl", "set-source-description", source_name, display_name],
                capture_output=True, timeout=5,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            self._destroy_channel(sink_attr, source_attr)
            return False

    def destroy_virtual_sink(self):
        # Unload all loopback modules first (tracked + orphaned) so PipeWire
        # doesn't reroute mic audio to the headset when the sinks disappear.
        self._disable_mic_passthrough_impl()
        self._unload_orphaned_loopbacks()
        self._destroy_channel("_source_module_id", "_sink_module_id")
        self._destroy_channel("_chat_source_module_id", "_chat_sink_module_id")
        # Fallback: unload any remaining orphaned gsboard modules
        self._unload_orphaned_modules()

    def _destroy_channel(self, *attr_names: str):
        for attr in attr_names:
            mod_id = getattr(self, attr, None)
            if mod_id:
                try:
                    subprocess.run(
                        ["pactl", "unload-module", mod_id],
                        capture_output=True, text=True, check=True, timeout=8,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
                setattr(self, attr, None)

    def _unload_orphaned_loopbacks(self):
        """Unload any loopback modules targeting gsboard sinks that aren't tracked."""
        gsboard_sinks = {self.sink_name, self.chat_sink_name}
        try:
            r = subprocess.run(
                ["pactl", "list", "modules", "short"],
                capture_output=True, text=True, timeout=8,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return
        for line in r.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 2:
                continue
            mod_id, mod_type = parts[0], parts[1]
            args = parts[2] if len(parts) > 2 else ""
            if mod_type != "module-loopback":
                continue
            if any(sink in args for sink in gsboard_sinks):
                try:
                    subprocess.run(
                        ["pactl", "unload-module", mod_id],
                        capture_output=True, text=True, timeout=8,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass

    def _unload_orphaned_modules(self):
        """Unload any gsboard pactl modules not tracked in instance variables."""
        gsboard_names = {
            self.sink_name, self.source_name,
            self.chat_sink_name, self.chat_source_name,
        }
        try:
            r = subprocess.run(
                ["pactl", "list", "modules", "short"],
                capture_output=True, text=True, timeout=8,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return
        for line in r.stdout.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 2:
                continue
            mod_id, mod_type = parts[0], parts[1]
            args = parts[2] if len(parts) > 2 else ""
            if mod_type not in ("module-null-sink", "module-remap-source", "module-loopback"):
                continue
            if any(name in args for name in gsboard_names):
                try:
                    subprocess.run(
                        ["pactl", "unload-module", mod_id],
                        capture_output=True, text=True, timeout=8,
                    )
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _is_active(self, name: str, kind: str) -> bool:
        try:
            r = subprocess.run(
                ["pactl", "list", kind, "short"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            return name in r.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    def is_sink_active(self) -> bool:
        return self.is_game_sink_active()

    def is_source_active(self) -> bool:
        return self.is_game_source_active()

    def get_virtual_mic_name(self) -> Optional[str]:
        return self.source_name if self.is_game_source_active() else None

    # ------------------------------------------------------------------
    # Device listing helpers
    # ------------------------------------------------------------------

    def list_sinks(self) -> List[Tuple[str, str]]:
        """Returns (name, description) for all sinks."""
        return self._list_devices("sinks")

    def list_sources(self) -> List[Tuple[str, str]]:
        """Returns (name, description) for all non-monitor sources."""
        results = []
        for name, desc in self._list_devices("sources"):
            if ".monitor" not in name:
                results.append((name, desc))
        return results

    def _list_devices(self, kind: str) -> List[Tuple[str, str]]:
        devices = []
        try:
            r = subprocess.run(
                ["pactl", "list", kind],
                capture_output=True, text=True, check=True, timeout=10,
            )
            name = None
            for line in r.stdout.splitlines():
                line = line.strip()
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Description:") and name:
                    desc = line.split(":", 1)[1].strip()
                    devices.append((name, desc))
                    name = None
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        return devices

    def get_sink_description(self, sink_name: str) -> Optional[str]:
        """Returns the human-readable description for a sink."""
        for name, desc in self.list_sinks():
            if name == sink_name:
                return desc
        return None

    def get_monitor_source_name(self) -> Optional[str]:
        try:
            r = subprocess.run(
                ["pactl", "list", "sources", "short"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                if f"{self.sink_name}.monitor" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        return None

    def get_sink_index(self) -> Optional[int]:
        try:
            r = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                if self.sink_name in line:
                    parts = line.split()
                    if parts:
                        return int(parts[0])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
            pass
        return None

    # ------------------------------------------------------------------
    # Mic passthrough via loopback modules (internal)
    # ------------------------------------------------------------------

    def _enable_mic_passthrough_impl(self, mic_source_name: str,
                                     volume: float) -> bool:
        """Loops the real mic into both virtual sinks using loopback modules."""
        self._disable_mic_passthrough_impl()
        vol_pa = int(volume * 65536)
        success = False
        for sink in (self.sink_name, self.chat_sink_name):
            if not self._is_active(sink, "sinks"):
                continue
            try:
                r = subprocess.run(
                    [
                        "pactl", "load-module", "module-loopback",
                        f"source={mic_source_name}",
                        f"sink={sink}",
                        f"volume={vol_pa}",
                        "latency_msec=20",
                    ],
                    capture_output=True, text=True, check=True, timeout=10,
                )
                self._loopback_module_ids.append(r.stdout.strip())
                success = True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                stderr = e.stderr.strip() if hasattr(e, "stderr") and e.stderr else ""
                print(f"[PipeWire] loopback to {sink} failed: {stderr}")
        return success

    def _disable_mic_passthrough_impl(self):
        for mod_id in self._loopback_module_ids:
            try:
                subprocess.run(
                    ["pactl", "unload-module", mod_id],
                    capture_output=True, text=True, check=True, timeout=8,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
        self._loopback_module_ids.clear()
