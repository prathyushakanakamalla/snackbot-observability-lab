"""PHASE 2: evaluate the evaluator. How often does the LLM judge agree with humans?

An LLM judge is only useful if it agrees with careful humans. This script compares, on every
answer that has both:
    HUMAN  user_feedback       (thumbs up/down from Streamlit or the API)
           human_correctness   (optional: a label you add yourself in the Phoenix UI)
    LLM    answer_correctness  (from scripts/run_evals.py)

Run:  python -m scripts.judge_agreement
"""
import pandas as pd

from snackbot import config
from snackbot.evals import phoenix_io

HUMAN_NAMES = ["user_feedback", "human_correctness"]
JUDGE_NAME = "answer_correctness"


def to_good(row) -> bool | None:
    """Collapse every label to good/bad. 'partially_correct' counts as bad: a user would not be happy."""
    if pd.notna(row.get("result.score")):
        return float(row["result.score"]) >= 1.0
    label = str(row.get("result.label", "")).lower()
    if label in ("correct", "thumbs_up", "good", "pass"):
        return True
    if label in ("incorrect", "partially_correct", "thumbs_down", "bad", "fail"):
        return False
    return None


def main():
    c = phoenix_io.client()
    roots = c.spans.get_spans_dataframe(query=phoenix_io.SpanQuery().where("span_kind == 'AGENT'"),
                                        project_name=config.PHOENIX_PROJECT, limit=phoenix_io.LIMIT)
    if roots.empty:
        raise SystemExit("No traces found.")
    ann = c.spans.get_span_annotations_dataframe(spans_dataframe=roots, project_identifier=config.PHOENIX_PROJECT,
                                                 include_annotation_names=HUMAN_NAMES + [JUDGE_NAME])
    if ann.empty:
        raise SystemExit("No annotations yet. Run run_evals.py and give some thumbs up/down first.")
    ann = ann.reset_index()
    span_col = "span_id" if "span_id" in ann else "context.span_id"
    ann["good"] = ann.apply(to_good, axis=1)

    human = ann[ann["annotation_name"].isin(HUMAN_NAMES)].groupby(span_col)["good"].last()
    judge = ann[ann["annotation_name"] == JUDGE_NAME].groupby(span_col)["good"].last()
    both = pd.concat([human.rename("human"), judge.rename("judge")], axis=1).dropna()
    if both.empty:
        raise SystemExit(f"No answer has both a human label and an LLM '{JUDGE_NAME}' label yet.\n"
                         "Tip: rate answers from a batch you have evaluated (the trace ids are in results/).")

    agree = (both["human"] == both["judge"]).mean()
    print(f"Answers with both labels: {len(both)}   agreement: {agree:.0%}\n")
    print(pd.crosstab(both["human"].map({True: "human: good", False: "human: bad"}),
                      both["judge"].map({True: "judge: good", False: "judge: bad"})), "\n")
    q = roots.set_index("context.span_id")["attributes.input.value"]
    for span_id, r in both[both["human"] != both["judge"]].iterrows():
        print(f"DISAGREE  human={'good' if r.human else 'bad'} judge={'good' if r.judge else 'bad'}  "
              f"span {span_id}: {str(q.get(span_id, ''))[:70]}")


if __name__ == "__main__":
    main()
