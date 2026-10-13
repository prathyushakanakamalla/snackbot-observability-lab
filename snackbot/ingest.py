"""Build the vector index: read docs -> split into chunks -> embed -> save to data/index/.

Run:  python -m snackbot.ingest
"""
import json
import re
from dataclasses import asdict, dataclass

import numpy as np

from snackbot import config
from snackbot.embeddings import embed


@dataclass
class Chunk:
    chunk_id: str   # e.g. "07_hr_leave_policy_2026#3"
    doc_id: str     # file name without extension
    title: str      # first "# " heading of the document
    section: str    # nearest "## " heading
    text: str


def _split_sections(markdown: str) -> list[tuple[str, str]]:
    """Split a markdown doc on '## ' headings. Returns (section_heading, section_text) pairs."""
    sections, current_heading, current_lines = [], "Introduction", []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if "".join(current_lines).strip():
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading, current_lines = line[3:].strip(), []
        else:
            current_lines.append(line)
    if "".join(current_lines).strip():
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return sections


def _window(text: str, size: int, overlap: int) -> list[str]:
    """Cut long text into overlapping character windows, preferring to break on newlines."""
    if len(text) <= size:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + size // 2, end)
            if newline != -1:
                end = newline
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in pieces if p]


def chunk_document(doc_id: str, markdown: str, size: int, overlap: int) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else doc_id
    chunks = []
    for section, body in _split_sections(markdown):
        for piece in _window(body, size, overlap):
            # Prefix the title + section so each chunk carries its own context into the embedding.
            text = f"{title} — {section}\n{piece}"
            chunks.append(Chunk(f"{doc_id}#{len(chunks)}", doc_id, title, section, text))
    return chunks


def build_index(size: int = config.CHUNK_SIZE, overlap: int = config.CHUNK_OVERLAP) -> int:
    all_chunks: list[Chunk] = []
    for path in sorted(config.DOCS_DIR.glob("*.md")):
        all_chunks += chunk_document(path.stem, path.read_text(encoding="utf-8"), size, overlap)

    vectors = embed([c.text for c in all_chunks])

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(config.INDEX_DIR / "embeddings.npy", vectors)
    (config.INDEX_DIR / "chunks.json").write_text(
        json.dumps([asdict(c) for c in all_chunks], indent=2), encoding="utf-8"
    )
    return len(all_chunks)


if __name__ == "__main__":
    n = build_index()
    print(f"Indexed {n} chunks from {config.DOCS_DIR} -> {config.INDEX_DIR}")
