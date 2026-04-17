import asyncio
import threading
from typing import Callable, Optional

from gsboard.input.hotkeys import SESSION_TYPE
from gsboard.models.sound import MacroConfig


class MacroEngine:
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._start_event_loop()

    def _start_event_loop(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def execute(
        self,
        macro: MacroConfig,
        play_fn: Callable,
        sound_id: str,
        file_path: str,
        volume: float,
    ):
        if not macro.key:
            play_fn(sound_id, file_path, volume)
            return
        asyncio.run_coroutine_threadsafe(
            self._run(macro, play_fn, sound_id, file_path, volume),
            self._loop,
        )

    async def _run(
        self,
        macro: MacroConfig,
        play_fn: Callable,
        sound_id: str,
        file_path: str,
        volume: float,
    ):
        controller = _get_keyboard_controller()
        key = _parse_key(macro.key)
        if key is None:
            play_fn(sound_id, file_path, volume)
            return

        if macro.pre_delay_ms > 0:
            await asyncio.sleep(macro.pre_delay_ms / 1000)

        try:
            controller.press(key)
        except Exception as e:
            print(f"[MacroEngine] key press failed: {e}")

        playing = play_fn(sound_id, file_path, volume)

        if playing is not None:
            await asyncio.get_event_loop().run_in_executor(None, playing.finished.wait)
        else:
            await asyncio.sleep(0.1)

        if macro.post_delay_ms > 0:
            await asyncio.sleep(macro.post_delay_ms / 1000)

        try:
            controller.release(key)
        except Exception as e:
            print(f"[MacroEngine] key release failed: {e}")

    def shutdown(self):
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


def _get_keyboard_controller():
    if SESSION_TYPE == "wayland":
        try:
            import evdev

            ui = evdev.UInput()
            return _EvdevController(ui)
        except Exception:
            pass
    from pynput.keyboard import Controller

    return Controller()


def _parse_key(key_str: str):
    if not key_str:
        return None
    if SESSION_TYPE == "wayland":
        try:
            from evdev import ecodes

            name = f"KEY_{key_str.upper()}"
            return getattr(ecodes, name, None)
        except ImportError:
            return None
    else:
        from pynput.keyboard import Key, KeyCode

        key_str_lower = key_str.lower()
        for k in Key:
            if k.name.lower() == key_str_lower:
                return k
        if len(key_str) == 1:
            return KeyCode.from_char(key_str)
        return None


class _EvdevController:
    def __init__(self, ui):
        self._ui = ui

    def press(self, code: int):
        from evdev import ecodes

        self._ui.write(ecodes.EV_KEY, code, 1)
        self._ui.syn()

    def release(self, code: int):
        from evdev import ecodes

        self._ui.write(ecodes.EV_KEY, code, 0)
        self._ui.syn()
