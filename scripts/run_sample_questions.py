"""Run every question in data/sample_questions.json and save the answers.

Run from the project root:  python -m scripts.run_sample_questions
Output: results/phase0_answers.md  (read it and judge the answers yourself — that's Phase 0's "eval")
"""
import json
import time
from pathlib import Path

from snackbot import config
from snackbot.agent import SnackBot

ROOT = Path(__file__).resolve().parent.parent


def main():
    questions = json.loads((ROOT / "data" / "sample_questions.json").read_text(encoding="utf-8"))
    bot = SnackBot()
    out = [f"# Phase 0 answers — model: {config.GROQ_MODEL}\n"]
    for q in questions:
        start = time.perf_counter()
        result = bot.answer(q["question"])
        seconds = time.perf_counter() - start
        print(f"[{q['id']}] {seconds:4.1f}s  tools={result.tools_used}")
        out.append(f"## {q['id']} ({q['category']})\n**Q:** {q['question']}\n\n**A:** {result.answer}\n\n"
                   f"_tools: {result.tools_used} · {seconds:.1f}s_\n")
        time.sleep(2)  # stay friendly with Groq's free-tier rate limits
    (ROOT / "results").mkdir(exist_ok=True)
    path = ROOT / "results" / "phase0_answers.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main()
