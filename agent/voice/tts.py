"""Text-to-speech via edge-tts (free, no GPU needed)."""

import os
import time
import asyncio
import edge_tts


_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "cache", "voice")
os.makedirs(_AUDIO_DIR, exist_ok=True)


class TTS:
    """Text-to-speech using edge-tts (Microsoft online TTS, free)."""

    def __init__(self, voice: str = "en-US-JennyNeural"):
        self.voice = voice

    async def speak(self, text: str) -> None:
        """Speak text aloud."""
        path = os.path.join(_AUDIO_DIR, f"response_{int(time.time())}.mp3")
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(path)

        if os.path.exists(path) and os.path.getsize(path) > 0:
            await asyncio.to_thread(self._play, path)
        self._cleanup(path)

    async def speak_and_wait(self, text: str) -> None:
        """Speak and wait for playback to finish."""
        await self.speak(text)

    def _play(self, path: str) -> None:
        """Play audio file. Tries simpleaudio, falls back to winsound."""
        try:
            import simpleaudio as sa
            import soundfile as sf
            data, sr = sf.read(path)
            play_obj = sa.play_buffer(
                (data * 32767).astype("int16"),
                1 if len(data.shape) == 1 else data.shape[1],
                2,
                sr,
            )
            play_obj.wait_done()
        except Exception:
            try:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
            except Exception:
                pass

    def _cleanup(self, path: str, delay: float = 2.0):
        """Remove audio file after a delay."""
        def _del():
            time.sleep(delay)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        thread = __import__("threading").Thread(target=_del, daemon=True)
        thread.start()

    async def save_to_file(self, text: str, path: str) -> str:
        """Save TTS audio to a specific file path."""
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(path)
        return path
