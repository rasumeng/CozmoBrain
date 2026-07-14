"""Voice listener with push-to-talk via pynput hotkey."""

import os
import time
import queue
import threading
import numpy as np

from .stt import STT


_HERE = os.path.dirname(__file__)
_AUDIO_DIR = os.path.join(_HERE, "..", "..", "cache", "voice")
os.makedirs(_AUDIO_DIR, exist_ok=True)

SAMPLE_RATE = 16000


class VoiceListener:
    """Push-to-talk voice listener.

    Holds a hotkey to record, releases to transcribe.
    Transcribed text is queued for the main loop to pick up.
    """

    def __init__(
        self,
        stt_model: str = "tiny",
        hotkey_name: str = "scroll_lock",
    ):
        self.stt = STT(stt_model)
        self.hotkey_name = hotkey_name
        self._hotkey = None
        self._recording = False
        self._stream = None
        self._audio_frames: list[np.ndarray] = []
        self._queue: queue.Queue[str] = queue.Queue()
        self._running = False
        self._listener_thread = None

    @property
    def hotkey(self):
        if self._hotkey is None:
            from pynput import keyboard
            mapping = {
                "scroll_lock": keyboard.Key.scroll_lock,
                "ctrl": keyboard.Key.ctrl,
                "shift": keyboard.Key.shift,
                "alt": keyboard.Key.alt,
                "pause": keyboard.Key.pause,
                "insert": keyboard.Key.insert,
                "f1": keyboard.Key.f1,
                "f2": keyboard.Key.f2,
                "f3": keyboard.Key.f3,
                "f4": keyboard.Key.f4,
            }
            key = mapping.get(self.hotkey_name)
            if key is None:
                key = keyboard.KeyCode.from_char(self.hotkey_name)
            self._hotkey = key
        return self._hotkey

    def start(self):
        """Start the keyboard listener in a background thread."""
        if self._running:
            return
        self._running = True
        self._listener_thread = threading.Thread(target=self._run, daemon=True)
        self._listener_thread.start()

    def stop(self):
        """Stop the listener."""
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=2)

    def has_pending(self) -> bool:
        """Check if voice input is waiting."""
        return not self._queue.empty()

    def get_pending(self) -> str | None:
        """Get next pending voice input, or None."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _run(self):
        """Keyboard listener loop."""
        from pynput import keyboard

        def on_press(key):
            if key == self.hotkey and not self._recording:
                self._start_recording()

        def on_release(key):
            if key == self.hotkey and self._recording:
                self._stop_recording()
                threading.Thread(target=self._transcribe, daemon=True).start()

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

    def _start_recording(self):
        """Begin audio capture."""
        self._recording = True
        self._audio_frames = []
        import sounddevice as sd

        self._stream = sd.InputStream(
            callback=self._audio_callback,
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=1024,
        )
        self._stream.start()

    def _stop_recording(self):
        """End audio capture."""
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio stream callback."""
        if self._recording:
            self._audio_frames.append(indata.copy())

    def _transcribe(self):
        """Transcribe recorded audio and queue result."""
        if not self._audio_frames:
            return

        try:
            audio = np.concatenate(self._audio_frames).flatten()

            # Trim silence at ends
            audio = self._trim_silence(audio)

            if len(audio) < SAMPLE_RATE * 0.3:
                return  # Too short

            text = self.stt.transcribe_array(audio, SAMPLE_RATE)
            if text.strip():
                self._queue.put(text.strip())
        except Exception:
            pass

    def _trim_silence(self, audio: np.ndarray, threshold: float = 0.02) -> np.ndarray:
        """Remove leading/trailing silence from audio."""
        indices = np.where(np.abs(audio) > threshold)[0]
        if len(indices) == 0:
            return audio
        return audio[indices[0]: indices[-1] + 1]
