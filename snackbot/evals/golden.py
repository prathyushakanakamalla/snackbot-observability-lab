"""The golden dataset: our agreed "right answers", written by a human who read the documents.

Each entry says what a good answer must contain (key_facts), must NOT contain (forbidden),
which documents should be retrieved (expected_docs), which tools should be used (expected_tools),
and whether SnackBot should decline (should_refuse). Evaluations compare real answers against it.
"""
import json
from functools import lru_cache

from snackbot import config


@lru_cache(maxsize=1)
def load_golden() -> dict[str, dict]:
    """Golden entries keyed by question id ("q01" ...)."""
    rows = json.loads(config.GOLDEN_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in rows}


def find(question_id: str | None = None, question: str | None = None) -> dict | None:
    golden = load_golden()
    if question_id and question_id in golden:
        return golden[question_id]
    if question:
        q = question.strip().lower()
        return next((g for g in golden.values() if g["question"].strip().lower() == q), None)
    return None
