"""PHASE 2: human feedback. A thumbs up/down from a user becomes a HUMAN annotation on the trace.

Human feedback is the most trusted (but sparsest) evaluation signal. Stored on the same span as the
LLM judge's scores, it lets you check the judge against people (scripts/judge_agreement.py).
"""
from snackbot import config

FEEDBACK_NAME = "user_feedback"


def log_feedback(span_id: str | None, thumbs_up: bool, comment: str | None = None,
                 user_id: str | None = None) -> bool:
    """Attach feedback to the root span of an answer. Returns False (never raises) if it can't."""
    if not span_id or config.TRACING != "full":
        return False
    try:
        from phoenix.client import Client

        Client(base_url=config.PHOENIX_ENDPOINT).spans.add_span_annotation(
            span_id=span_id,
            annotation_name=FEEDBACK_NAME,
            annotator_kind="HUMAN",
            label="thumbs_up" if thumbs_up else "thumbs_down",
            score=1.0 if thumbs_up else 0.0,
            explanation=comment or None,
            metadata={"user_id": user_id} if user_id else None,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - feedback must never break the chat
        print(f"[feedback] could not log feedback: {exc}")
        return False
