"""Vector search over the saved index. Deliberately plain numpy so you can see every step."""
import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from snackbot import config
from snackbot.embeddings import embed


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    section: str
    text: str
    score: float  # cosine similarity, higher = more similar


@lru_cache(maxsize=1)
def _load_index():
    chunks_path = config.INDEX_DIR / "chunks.json"
    if not chunks_path.exists():
        raise FileNotFoundError("No index found. Run:  python -m snackbot.ingest")
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    vectors = np.load(config.INDEX_DIR / "embeddings.npy")
    return chunks, vectors


def retrieve(query: str, top_k: int = config.TOP_K) -> list[RetrievedChunk]:
    chunks, vectors = _load_index()
    query_vec = embed([query])[0]
    scores = vectors @ query_vec                 # cosine similarity (vectors are normalised)
    best = np.argsort(-scores)[:top_k]
    return [
        RetrievedChunk(
            chunk_id=chunks[i]["chunk_id"],
            doc_id=chunks[i]["doc_id"],
            section=chunks[i]["section"],
            text=chunks[i]["text"],
            score=float(scores[i]),
        )
        for i in best
    ]
