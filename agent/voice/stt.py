"""Speech-to-text via faster-whisper. CPU-friendly with tiny model by default."""

import os
import numpy as np


_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "cache", "voice")
os.makedirs(_AUDIO_DIR, exist_ok=True)


class STT:
    """Local speech-to-text using faster-whisper."""

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None

    def _lazy_load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text."""
        self._lazy_load()
        segments, _ = self._model.transcribe(audio_path, language="en")
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip())

    def transcribe_array(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe a numpy audio array directly."""
        self._lazy_load()
        segments, _ = self._model.transcribe(
            audio.astype(np.float32),
            sample_rate=sample_rate,
            language="en",
        )
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip())

    @property
    def is_loaded(self) -> bool:
        return self._model is not None
