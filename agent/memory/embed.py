"""Embedding wrapper using sentence-transformers."""

import numpy as np


class MemoryEmbedder:
    """Local embedding via sentence-transformers. CPU-friendly."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._dim = 384

    def _lazy_load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self.model_name,
                device="cpu",
            )
            self._dim = self._model.get_embedding_dimension()

    @property
    def dim(self) -> int:
        self._lazy_load()
        return self._dim

    def encode(self, texts: list[str]) -> np.ndarray:
        """Encode texts into embedding vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            np.ndarray of shape (len(texts), dim).
        """
        if not texts:
            return np.array([], dtype=np.float32)

        self._lazy_load()
        embeddings = self._model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def encode_one(self, text: str) -> list[float]:
        """Encode a single text string."""
        vec = self.encode([text])[0]
        return vec.tolist()
