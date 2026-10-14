"""Vector search over the saved index. Deliberately plain numpy so you can see every step."""
import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from openinference.semconv.trace import DocumentAttributes, EmbeddingAttributes, SpanAttributes

from snackbot import config
from snackbot.embeddings import embed
from snackbot.tracing import SpanKind, start_span, to_json


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
    # PHASE 1: a RETRIEVER span. Phoenix shows its documents as a ranked list with scores.
    with start_span("retrieve", SpanKind.RETRIEVER, input_value=query,
                    **{"retrieval.top_k": top_k}) as span:
        chunks, vectors = _load_index()

        # PHASE 1: a child EMBEDDING span, so you can see how long embedding the query takes.
        with start_span("embed_query", SpanKind.EMBEDDING, **{
            SpanAttributes.EMBEDDING_MODEL_NAME: config.EMBED_MODEL,
            f"{SpanAttributes.EMBEDDING_EMBEDDINGS}.0.{EmbeddingAttributes.EMBEDDING_TEXT}": query,
        }):
            query_vec = embed([query])[0]

        scores = vectors @ query_vec                 # cosine similarity (vectors are normalised)
        best = np.argsort(-scores)[:top_k]
        results = [
            RetrievedChunk(
                chunk_id=chunks[i]["chunk_id"],
                doc_id=chunks[i]["doc_id"],
                section=chunks[i]["section"],
                text=chunks[i]["text"],
                score=float(scores[i]),
            )
            for i in best
        ]

        # PHASE 1: record every retrieved document using the OpenInference naming convention:
        #   retrieval.documents.<n>.document.id / .content / .score / .metadata
        for n, r in enumerate(results):
            prefix = f"{SpanAttributes.RETRIEVAL_DOCUMENTS}.{n}"
            span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_ID}", r.chunk_id)
            span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_CONTENT}", r.text)
            span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_SCORE}", r.score)
            span.set_attribute(f"{prefix}.{DocumentAttributes.DOCUMENT_METADATA}",
                               to_json({"doc_id": r.doc_id, "section": r.section}))
        return results
