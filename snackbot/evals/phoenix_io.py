"""Read SnackBot traces out of Phoenix, and write evaluation results back in as annotations.

This is the core Phoenix evaluation loop:

    traces in Phoenix ──read──► Python (run evals) ──write annotations──► same traces in Phoenix

Annotations are labels/scores attached to a span (or to one retrieved document of a span).
Phoenix shows them in the UI, lets you filter on them, and charts them over time.
"""
from dataclasses import dataclass, field

import pandas as pd
from phoenix.client import Client
from phoenix.client.types.spans import SpanQuery

from snackbot import config

LIMIT = 10_000  # max spans fetched per query


def client() -> Client:
    return Client(base_url=config.PHOENIX_ENDPOINT)


@dataclass
class RetrievedDoc:
    position: int     # rank in the result list (0 = top)
    chunk_id: str
    doc_id: str
    content: str
    score: float


@dataclass
class Retrieval:
    span_id: str      # the RETRIEVER span
    query: str
    docs: list[RetrievedDoc]


@dataclass
class Run:
    """Everything we know about one SnackBot answer (one trace)."""
    span_id: str      # the root AGENT span: where answer-level annotations go
    trace_id: str
    question: str
    answer: str
    status: str
    latency_ms: float
    metadata: dict
    tags: list[str]
    tools_used: list[str]
    retrievals: list[Retrieval] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)  # what every tool returned = the model's context

    @property
    def question_id(self):
        return self.metadata.get("question_id")

    @property
    def context(self) -> str:
        return "\n\n".join(self.tool_outputs)


def _spans(c: Client, where: str) -> pd.DataFrame:
    df = c.spans.get_spans_dataframe(query=SpanQuery().where(where), project_name=config.PHOENIX_PROJECT,
                                     limit=LIMIT, timeout=60)
    return df.reset_index(drop=True) if not df.empty else df


def _as_list(value) -> list:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return list(value)


def latest_batch_tag(c: Client | None = None) -> str | None:
    """The tag of the most recent run of scripts/run_sample_questions.py."""
    c = c or client()
    roots = _spans(c, "span_kind == 'AGENT'")
    if roots.empty or "attributes.tag.tags" not in roots:
        return None
    tags = {t for ts in roots["attributes.tag.tags"] for t in _as_list(ts) if str(t).startswith("batch-")}
    return max(tags) if tags else None


def load_runs(tag: str | None = None, c: Client | None = None) -> list[Run]:
    """Load every SnackBot trace carrying `tag` (or all traces if tag is None)."""
    c = c or client()
    roots = _spans(c, "span_kind == 'AGENT'")
    if roots.empty:
        return []
    if tag:
        roots = roots[roots["attributes.tag.tags"].apply(lambda ts: tag in _as_list(ts))]
    trace_ids = set(roots["context.trace_id"])

    retrievers = _spans(c, "span_kind == 'RETRIEVER'")
    tools = _spans(c, "span_kind == 'TOOL'")
    if not retrievers.empty:
        retrievers = retrievers[retrievers["context.trace_id"].isin(trace_ids)].sort_values("start_time")
    if not tools.empty:
        tools = tools[tools["context.trace_id"].isin(trace_ids)].sort_values("start_time")

    runs = []
    for _, r in roots.iterrows():
        agent_attrs = r.get("attributes.agent")
        agent_attrs = agent_attrs if isinstance(agent_attrs, dict) else {}
        run = Run(
            span_id=r["context.span_id"], trace_id=r["context.trace_id"],
            question=r.get("attributes.input.value") or "", answer=r.get("attributes.output.value") or "",
            status=r.get("status_code") or "UNSET",
            latency_ms=(r["end_time"] - r["start_time"]).total_seconds() * 1000,
            metadata=r.get("attributes.metadata") if isinstance(r.get("attributes.metadata"), dict) else {},
            tags=_as_list(r.get("attributes.tag.tags")),
            tools_used=_as_list(agent_attrs.get("tools_used")),
        )
        if not retrievers.empty:
            for _, s in retrievers[retrievers["context.trace_id"] == run.trace_id].iterrows():
                docs = []
                for pos, d in enumerate(_as_list(s.get("attributes.retrieval.documents"))):
                    meta = d.get("document.metadata") or {}
                    docs.append(RetrievedDoc(pos, d.get("document.id", ""), meta.get("doc_id", ""),
                                             d.get("document.content", ""), float(d.get("document.score") or 0)))
                run.retrievals.append(Retrieval(s["context.span_id"], s.get("attributes.input.value") or "", docs))
        if not tools.empty:
            outs = tools[tools["context.trace_id"] == run.trace_id]["attributes.output.value"]
            run.tool_outputs = [o for o in outs if isinstance(o, str)]
        runs.append(run)
    return sorted(runs, key=lambda x: (x.question_id or "zz", x.trace_id))


def log_span_annotations(rows: list[dict], annotator_kind: str, c: Client | None = None):
    """rows: [{"span_id", "name", "label", "score", "explanation"}]. Re-running overwrites (upsert)."""
    if not rows:
        return
    df = pd.DataFrame(rows).rename(columns={"name": "annotation_name"})
    (c or client()).spans.log_span_annotations_dataframe(dataframe=df, annotator_kind=annotator_kind, sync=True)


def log_document_annotations(rows: list[dict], annotator_kind: str, c: Client | None = None):
    """rows: [{"span_id", "document_position", "name", "label", "score", "explanation"}]."""
    if not rows:
        return
    df = pd.DataFrame(rows).rename(columns={"name": "annotation_name"})
    (c or client()).spans.log_document_annotations_dataframe(dataframe=df, annotator_kind=annotator_kind,
                                                            sync=True)
