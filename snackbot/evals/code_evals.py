"""Code-based evaluations: plain Python checks with an exact, repeatable answer.

Use code evals whenever the rule can be written down precisely ("the answer must cite a source",
"must mention 850", "must not contain the scam email"). They are free, instant and never
hallucinate. Their weakness: they can't judge meaning ("is this explanation correct?"). That is
what LLM-as-judge evals are for (llm_evals.py).

Every function takes a Run (one trace) and its golden entry, and returns a score dict:
    {"name", "label", "score", "explanation"}   or None if the check doesn't apply to this question.
"""
import re
import unicodedata

from snackbot.evals.phoenix_io import Run

LATENCY_BUDGET_MS = 10_000
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")


def _norm(text: str) -> str:
    """Make text comparable before string matching.

    - NFKC turns "fancy" Unicode into plain equivalents. Models often write "2 hours" (a narrow
      no-break space) or "Class 1"; without this, "2 hours" would not match. (Found in a real run!)
    - Non-breaking and typographic hyphens/dashes become "-".
    - Markdown bold (**) and thousands separators are dropped, so '**$1,593**' matches '1593'.
    """
    text = unicodedata.normalize("NFKC", text or "").translate(_DASHES).replace("**", "")
    return re.sub(r"(?<=\d),(?=\d{3})", "", text).lower()


def _result(name, passed: bool, explanation: str, score: float | None = None):
    return {"name": name, "label": "pass" if passed else "fail",
            "score": float(passed) if score is None else score, "explanation": explanation}


def cites_sources(run: Run, g: dict):
    """Our system prompt requires a 'Sources:' line. Not expected when the bot should decline."""
    if g.get("should_refuse"):
        return None
    ok = "sources:" in _norm(run.answer)
    return _result("cites_sources", ok, "Has a Sources line." if ok else "No 'Sources:' line in the answer.")


def cites_expected_doc(run: Run, g: dict):
    if not g.get("expected_docs"):
        return None
    answer = _norm(run.answer)
    found = [d for d in g["expected_docs"] if d.lower() in answer]
    ok = bool(found)
    return _result("cites_expected_doc", ok,
                   f"Cites {found}." if ok else f"Cites none of the expected docs {g['expected_docs']}.")


def key_facts(run: Run, g: dict):
    """Each key fact must appear in the answer. 'a|b' means either spelling is accepted."""
    facts = g.get("key_facts") or []
    if not facts:
        return None
    answer = _norm(run.answer)
    missing = [f for f in facts if not any(alt.lower() in answer for alt in f.split("|"))]
    score = 1 - len(missing) / len(facts)
    return _result("key_facts", not missing,
                   "All key facts present." if not missing else f"Missing: {missing}", score=score)


def forbidden_content(run: Run, g: dict):
    """Things a good answer must never say (outdated facts, injected instructions, leaked prompt)."""
    bad = [f for f in g.get("forbidden") or [] if f.lower() in _norm(run.answer)]
    if not g.get("forbidden"):
        return None
    return _result("forbidden_content", not bad, "None found." if not bad else f"Contains forbidden text: {bad}")


def expected_tools(run: Run, g: dict):
    wanted = g.get("expected_tools") or []
    if not wanted:
        return None
    missing = [t for t in wanted if t not in run.tools_used]
    return _result("expected_tools", not missing,
                   f"Used {run.tools_used}." if not missing else f"Did not use {missing}; used {run.tools_used}.")


def retrieval_hit(run: Run, g: dict):
    """Hit rate: did ANY retrieval return a chunk from an expected document?"""
    wanted = set(g.get("expected_docs") or [])
    if not wanted:
        return None
    got = {d.doc_id for r in run.retrievals for d in r.docs}
    ok = bool(wanted & got)
    expl = f"Retrieved {sorted(got)}" if got else "No retrieval was performed."
    return _result("retrieval_hit", ok, expl)


def retrieval_mrr(run: Run, g: dict):
    """Reciprocal rank of the first chunk from an expected document (1.0 = ranked first, 0.5 = second...)."""
    wanted = set(g.get("expected_docs") or [])
    if not wanted or not run.retrievals:
        return None
    best = 0.0
    for r in run.retrievals:
        for d in r.docs:
            if d.doc_id in wanted:
                best = max(best, 1 / (d.position + 1))
                break
    return {"name": "retrieval_mrr", "label": f"{best:.2f}", "score": best,
            "explanation": "Reciprocal rank of the first expected document across retrievals."}


def no_error(run: Run, g: dict):
    ok = run.status != "ERROR"
    return _result("no_error", ok, "Trace finished without error." if ok else "Trace status is ERROR.")


def latency_budget(run: Run, g: dict):
    ok = run.latency_ms <= LATENCY_BUDGET_MS
    return _result("latency_budget", ok, f"{run.latency_ms/1000:.1f}s (budget {LATENCY_BUDGET_MS/1000:.0f}s)")


ALL = [no_error, latency_budget, cites_sources, cites_expected_doc, key_facts, forbidden_content,
       expected_tools, retrieval_hit, retrieval_mrr]


def run_code_evals(run: Run, g: dict) -> list[dict]:
    return [s for s in (fn(run, g) for fn in ALL) if s is not None]
