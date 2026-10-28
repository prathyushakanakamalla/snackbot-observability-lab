"""PHASE 2: evaluate a batch of SnackBot traces and write the results back into Phoenix.

Typical use (from the project root, with Phoenix running):
    python -m scripts.run_sample_questions     # 1. produce traces (prints a batch tag)
    python -m scripts.run_evals                # 2. evaluate the latest batch

Options:
    --tag batch-20261014-101500   evaluate a specific batch (default: the latest one)
    --skip-llm                    code evals only (instant, no Groq calls)
    --skip-docs                   skip per-document relevance judging (halves the judge calls)
    --judge-model MODEL           e.g. openai/gpt-oss-20b (faster, separate rate limits)

What it does:
    1. Reads the batch's traces from Phoenix (question, answer, retrieved docs, tool outputs).
    2. Runs code evals and LLM-as-judge evals against the golden dataset.
    3. Logs every result back to Phoenix as an annotation on the right span or document.
    4. Writes results/eval_<tag>.md (summary) and results/eval_<tag>.csv (every score).
"""
import argparse
import time

import pandas as pd

from snackbot import config
from snackbot.evals import code_evals, golden, phoenix_io

ANSWER_LEVEL_LLM = ["answer_correctness", "faithfulness", "refusal"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--skip-docs", action="store_true")
    ap.add_argument("--judge-model")
    args = ap.parse_args()

    c = phoenix_io.client()
    tag = args.tag or phoenix_io.latest_batch_tag(c)
    if not tag:
        raise SystemExit("No batch found. Run:  python -m scripts.run_sample_questions")
    runs = phoenix_io.load_runs(tag, c)
    print(f"Evaluating {len(runs)} traces from {tag} in project '{config.PHOENIX_PROJECT}'")

    judges = None
    if not args.skip_llm:
        from snackbot.evals.llm_evals import Judges
        judges = Judges(args.judge_model)
        print(f"Judge model: {judges.model}")

    code_rows, llm_rows, doc_rows, table = [], [], [], []
    for i, run in enumerate(runs, 1):
        g = golden.find(run.question_id, run.question) or {}
        start = time.perf_counter()
        scores = {}

        # ---- 1. code evals (always) -------------------------------------------------------------
        for s in code_evals.run_code_evals(run, g):
            code_rows.append({"span_id": run.span_id, **s})
            scores[s["name"]] = s

        # ---- 2. LLM-as-judge evals ----------------------------------------------------------------
        if judges:
            if g:
                scores["answer_correctness"] = judges.correctness_of(run.question, run.answer, g["reference_answer"])
            if run.context:  # faithfulness needs something to be faithful TO
                scores["faithfulness"] = judges.faithfulness_of(run.question, run.answer, run.context)
            scores["refusal"] = judges.refusal_of(run.question, run.answer)
            for name in ANSWER_LEVEL_LLM:
                if name in scores:
                    llm_rows.append({"span_id": run.span_id, **scores[name]})

            # A code eval built on an LLM eval: did it decline exactly when it should have?
            if g and scores["refusal"]["label"] in ("refused", "answered"):
                refused = scores["refusal"]["label"] == "refused"
                ok = refused == g["should_refuse"]
                s = {"name": "refusal_appropriate", "label": "pass" if ok else "fail", "score": float(ok),
                     "explanation": f"refused={refused}, should_refuse={g['should_refuse']}"}
                code_rows.append({"span_id": run.span_id, **s})
                scores[s["name"]] = s

            # ---- 3. retrieval quality: judge each retrieved document ----------------------------
            if not args.skip_docs:
                for r in run.retrievals:
                    labels = []
                    for d in r.docs:
                        rel = judges.relevance_of(run.question, d.content)
                        doc_rows.append({"span_id": r.span_id, "document_position": d.position, **rel})
                        if rel["score"] is not None:
                            labels.append(rel["score"])
                    if labels:  # precision@k for this search = share of returned docs that were relevant
                        p = sum(labels) / len(labels)
                        llm_rows.append({"span_id": r.span_id, "name": "retrieval_precision", "label": f"{p:.2f}",
                                         "score": p, "explanation": f"{int(sum(labels))}/{len(labels)} documents relevant"})
                        scores.setdefault("retrieval_precision", {"score": p})

        table.append({"question_id": run.question_id, "category": g.get("category", run.metadata.get("category")),
                      "question": run.question, "trace_id": run.trace_id,
                      **{k: v.get("score") for k, v in scores.items()},
                      **{f"{k}__why": v.get("explanation") for k, v in scores.items()
                         if k in ("answer_correctness", "faithfulness", "key_facts", "refusal_appropriate")}})
        print(f"[{i:2}/{len(runs)}] {run.question_id or '-':4} {time.perf_counter() - start:5.1f}s  "
              + "  ".join(f"{k}={v['score']:.2f}" for k, v in scores.items()
                          if v.get("score") is not None and k in ("answer_correctness", "faithfulness", "key_facts")))

    # ---- 4. write everything back to Phoenix --------------------------------------------------
    phoenix_io.log_span_annotations(code_rows, "CODE", c)
    phoenix_io.log_span_annotations([r for r in llm_rows if r["score"] is not None], "LLM", c)
    phoenix_io.log_document_annotations([r for r in doc_rows if r["score"] is not None], "LLM", c)
    print(f"\nLogged {len(code_rows)} code, {len(llm_rows)} LLM and {len(doc_rows)} document annotations to Phoenix.")

    write_report(pd.DataFrame(table), tag, judges.model if judges else None)


def write_report(df: pd.DataFrame, tag: str, judge_model: str | None):
    config.RESULTS_DIR.mkdir(exist_ok=True)
    df.to_csv(config.RESULTS_DIR / f"eval_{tag}.csv", index=False)
    metrics = [m for m in ["answer_correctness", "faithfulness", "refusal_appropriate", "key_facts",
                           "forbidden_content", "cites_sources", "cites_expected_doc", "expected_tools",
                           "retrieval_hit", "retrieval_mrr", "retrieval_precision", "no_error", "latency_budget"]
               if m in df]
    lines = [f"# Evaluation report: {tag}", "",
             f"Model under test: {config.GROQ_MODEL} · judge: {judge_model or 'none (code evals only)'} · "
             f"{len(df)} questions", "", "## Overall (mean score, 0–1; n = questions where the eval applies)", "",
             "| Eval | Mean | n |", "|---|---|---|"]
    for m in metrics:
        col = pd.to_numeric(df[m], errors="coerce").dropna()
        lines.append(f"| {m} | {col.mean():.2f} | {len(col)} |")
    if "answer_correctness" in df:
        lines += ["", "## By category (mean answer_correctness)", "", "| Category | Correctness | n |", "|---|---|---|"]
        for cat, grp in df.groupby("category"):
            col = pd.to_numeric(grp["answer_correctness"], errors="coerce").dropna()
            lines.append(f"| {cat} | {col.mean():.2f} | {len(col)} |")
    lines += ["", "## Needs attention", ""]
    for _, r in df.iterrows():
        # retrieval_mrr / retrieval_precision below 1.0 are normal (top-k returns extra chunks), so they
        # are reported in the table above but don't by themselves put a question on this list.
        problems = [m for m in metrics if pd.notna(r.get(m)) and float(r[m]) < 1.0
                    and m not in ("retrieval_mrr", "retrieval_precision")]
        if problems:
            lines.append(f"### {r['question_id']} ({r['category']}): {r['question']}")
            lines.append(f"- trace: `{r['trace_id']}`")
            lines.append(f"- failing: {', '.join(f'{p}={float(r[p]):.2f}' for p in problems)}")
            for k in ("answer_correctness", "faithfulness", "key_facts", "refusal_appropriate"):
                why = r.get(f"{k}__why")
                if isinstance(why, str) and k in problems:
                    lines.append(f"- {k}: {why}")
            lines.append("")
    path = config.RESULTS_DIR / f"eval_{tag}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {path}")
    print("\n".join(lines[: 6 + len(metrics) + 2]))


if __name__ == "__main__":
    main()
