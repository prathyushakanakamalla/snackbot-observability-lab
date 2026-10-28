"""Run every question in data/sample_questions.json and save the answers.

Run from the project root:  python -m scripts.run_sample_questions
Output: results/phase1_answers.md, with a trace id per answer so you can open it in Phoenix.
"""
import json
import time
from pathlib import Path

from snackbot import config
from snackbot.agent import SnackBot
from snackbot.tracing import flush, setup_tracing

ROOT = Path(__file__).resolve().parent.parent


def main():
    setup_tracing()
    questions = json.loads((ROOT / "data" / "sample_questions.json").read_text(encoding="utf-8"))
    bot = SnackBot()
    run_tag = f"batch-{time.strftime('%Y%m%d-%H%M%S')}"  # PHASE 1: tag lets you filter this run's traces
    out = [f"# Sample answers — model: {config.GROQ_MODEL} · tracing: {config.TRACING} · tag: {run_tag}\n"]
    for q in questions:
        start = time.perf_counter()
        result = bot.answer(q["question"], user_id="batch-script", tags=[run_tag, q["category"]],
                            metadata={"interface": "batch", "question_id": q["id"], "category": q["category"]})
        seconds = time.perf_counter() - start
        print(f"[{q['id']}] {seconds:4.1f}s  tools={result.tools_used}  trace={result.trace_id}")
        out.append(f"## {q['id']} ({q['category']})\n**Q:** {q['question']}\n\n**A:** {result.answer}\n\n"
                   f"_tools: {result.tools_used} · {seconds:.1f}s · trace: {result.trace_id}_\n")
        time.sleep(2)  # stay friendly with Groq's free-tier rate limits
    flush()  # PHASE 1: make sure every span reaches Phoenix before the script exits
    (ROOT / "results").mkdir(exist_ok=True)
    path = ROOT / "results" / "phase1_answers.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"\nSaved {path}")
    print(f"Batch tag: {run_tag}\nNext (Phase 2):  python -m scripts.run_evals --tag {run_tag}")


if __name__ == "__main__":
    main()
