"""Local, free embeddings with sentence-transformers. The model downloads once (~90 MB) on first use."""
from functools import lru_cache

import numpy as np

from snackbot import config


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # imported lazily: it is slow to load

    return SentenceTransformer(config.EMBED_MODEL)


def embed(texts: list[str]) -> np.ndarray:
    """Return L2-normalised embeddings, shape (len(texts), dim). Normalised => dot product == cosine."""
    vectors = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype=np.float32)
