# Phase 2 — Evaluation

**Goal:** stop judging answers by eye. By the end, every SnackBot answer in a batch gets scored
automatically, the scores live on the traces in Phoenix, and you can trust (and question) them.

In Phase 1 you could explain *one* bad answer by reading its trace. That doesn't scale to thousands of
answers, and it can't tell you whether a change made things better overall. Evaluation turns
"I think it's worse" into "correctness dropped from 0.85 to 0.70 on conflicting-docs questions".

## 1. What changed

| File | What it does |
|---|---|
| `data/golden_dataset.json` | **New.** 20 questions with a reference answer, key facts, forbidden text, expected docs and tools, and whether SnackBot should decline. The "answer key". |
| `snackbot/evals/golden.py` | **New.** Loads the golden dataset. |
| `snackbot/evals/phoenix_io.py` | **New.** Reads traces from Phoenix (question, answer, retrieved docs, tool outputs) and writes results back as **annotations**. |
| `snackbot/evals/code_evals.py` | **New.** 9 deterministic checks: sources cited, key facts present, forbidden text absent, expected tools used, retrieval hit rate and MRR, no error, latency budget. |
| `snackbot/evals/llm_evals.py` | **New.** LLM-as-judge: Phoenix's built-in faithfulness, refusal and retrieval-relevance judges, plus our own reference-based correctness judge. Groq `gpt-oss-120b` is the judge. |
| `snackbot/feedback.py` | **New.** Turns a thumbs up/down into a HUMAN annotation on the trace. |
| `scripts/run_evals.py` | **New.** The pipeline: read a batch → run all evals → log annotations → write `results/eval_<tag>.md` and `.csv`. |
| `scripts/judge_agreement.py` | **New.** Compares human labels with the LLM judge ("evaluating the evaluator"). |
| `app_streamlit.py` | Thumbs up/down under every answer. |
| `api.py` | New `POST /feedback` endpoint. |
| `scripts/run_sample_questions.py` | Prints the batch tag and the next command. |
| `snackbot/config.py`, `.env.example` | `JUDGE_MODEL` setting. |
| `snackbot/tracing.py` | Unchanged from your version (your thread-lock fix for Streamlit is kept). |

## 2. The ideas

### Three kinds of evaluator

| Kind | How | Good at | Weak at | In SnackBot |
|---|---|---|---|---|
| **Code** | Plain Python rules | Exact, free, instant, repeatable | Can't judge meaning | `key_facts`, `cites_sources`, `retrieval_hit`… |
| **LLM-as-judge** | A second LLM grades with a prompt | Meaning, nuance, any wording | Costs tokens, slow, can be wrong or biased | `answer_correctness`, `faithfulness`, `refusal`, `retrieval_relevance` |
| **Human** | People label answers | The ground truth | Slow, expensive, sparse | `user_feedback` thumbs, labels you add in the UI |

Real systems use all three. Code evals catch the obvious; LLM judges scale judgement; humans keep the
judges honest.

### Reference-based vs reference-free

- **Reference-based** evals compare against a known right answer: `answer_correctness`, `key_facts`,
  `retrieval_hit`. They need a golden dataset, so they only work offline on prepared questions.
- **Reference-free** evals need no answer key: `faithfulness` (is the answer supported by what was
  retrieved?), `refusal`, `retrieval_relevance`. They can run on *live* traffic (Phase 4).

### What each eval tells you

| Eval | Question it answers | Annotated on |
|---|---|---|
| `answer_correctness` | Does the answer match the reference? (correct / partially_correct / incorrect) | root AGENT span |
| `faithfulness` | Is every claim supported by what the tools returned? Unfaithful = **hallucination** | root span |
| `refusal` | Did SnackBot decline to answer? | root span |
| `refusal_appropriate` | Did it decline exactly when it should have? | root span |
| `key_facts` / `forbidden_content` | Are the must-have facts there, and the must-not-say text absent? | root span |
| `cites_sources` / `cites_expected_doc` | Did it cite, and cite the right document? | root span |
| `expected_tools` | Did it use the tools the question needs? | root span |
| `retrieval_hit` | Did any search return a chunk from the right document? (hit rate) | root span |
| `retrieval_mrr` | How high was the first right chunk ranked? 1.0 = first, 0.5 = second (mean reciprocal rank) | root span |
| `retrieval_relevance` | Is this one retrieved chunk relevant to the question? | each **document** of the RETRIEVER span |
| `retrieval_precision` | What share of the retrieved chunks were relevant? (precision@k) | RETRIEVER span |
| `no_error` / `latency_budget` | Did it finish cleanly, within 10 seconds? | root span |
| `user_feedback` | Did the user like it? | root span (HUMAN) |

### Reading the combinations is where the insight is

| Correctness | Faithfulness | Retrieval hit | Most likely cause |
|---|---|---|---|
| incorrect | faithful | hit | The context contained wrong or outdated info and the model repeated it (e.g. the archived HR policy). **Data / retrieval ranking problem.** |
| incorrect | unfaithful | — | The model made something up. **Hallucination**: prompt or model problem. |
| incorrect | faithful | miss | The right document was never found. **Retrieval problem** (chunking, embeddings, the model's search query). |
| correct | unfaithful | — | Right by luck or from the model's own knowledge, not from your documents. Risky. |

### Designing a judge (look at `llm_evals.py`)

- **Narrow labels**, not "rate 1–10". `correct / partially_correct / incorrect` is far more consistent.
- **Ask for an explanation.** Phoenix stores it with the label; it's how you audit the judge.
- **Structured output.** The judge must return JSON matching a schema. On Groq only the `gpt-oss`
  models support this, which is why the judge isn't the app's Llama model.
- **A different model family** from the one being judged reduces "self-preference" bias.
- **Evaluate the evaluator.** A judge is a model too. Measure its agreement with humans before you
  trust its numbers (Lab 7).

## 3. Setup

```powershell
pip install -r requirements.txt     # adds arize-phoenix-evals, arize-phoenix-client, openai, pandas
```

Optional, in `.env`: `JUDGE_MODEL=openai/gpt-oss-120b` (the default). If that model is slow or
rate-limited, use `openai/gpt-oss-20b`.

**Time and rate limits.** A full run makes about 6–8 judge calls per question (correctness,
faithfulness, refusal, and one per retrieved document), so 20 questions is about 140 calls. On the free
tier that takes roughly 5–15 minutes; retries on rate limits are automatic. Use `--skip-docs` to halve
it, or `--skip-llm` for code evals only (instant).

## 4. Labs

Keep `phoenix serve` running in one terminal for all of these.

### Lab 1 — Code evals only

```powershell
python -m scripts.run_sample_questions        # prints a batch tag
python -m scripts.run_evals --skip-llm        # evaluates the latest batch
```

Open `results/eval_<tag>.md`. Then in Phoenix open any root span from the batch: the **Annotations**
section now lists `key_facts`, `cites_sources` and so on, each with a label, score and explanation. On
the Spans tab the **annotations** column shows them as chips.

### Lab 2 — The full evaluation

```powershell
python -m scripts.run_evals
```

Read the report's "Overall" and "By category" tables. Compare them with the grades you gave by hand in
Phase 0. Where do you and the judge disagree?

### Lab 3 — Filter by evaluation results

In Phoenix's span filter (these were tested):

| Filter | Shows |
|---|---|
| `annotations['answer_correctness'].label == 'incorrect'` | Every wrong answer |
| `annotations['faithfulness'].label == 'unfaithful'` | Hallucinations |
| `annotations['answer_correctness'].label == 'incorrect' and annotations['faithfulness'].label == 'faithful'` | "Faithfully wrong": bad data or bad ranking |
| `annotations['key_facts'].label == 'fail'` | Missing must-have facts |
| `annotations['refusal_appropriate'].label == 'fail'` | Declined when it shouldn't (or vice versa) |
| `annotations['user_feedback'].label == 'thumbs_down'` | What users disliked |

For each "faithfully wrong" answer, open the trace and confirm the cause in the retrieve span.

### Lab 4 — Read the judge's explanations

Open three `answer_correctness` annotations: one correct, one partially correct, one incorrect. Is the
explanation convincing? Would you have given the same label? Write down any you disagree with.

### Lab 5 — Document-level relevance

Open a `retrieve` span from the batch → Documents. Each document now carries a `retrieval_relevance`
annotation. Find a search where most chunks were judged irrelevant. Was the problem the model's search
query (the span's input) or the documents themselves?

### Lab 6 — Human feedback

Run `streamlit run app_streamlit.py`, ask a few questions, and click 👍 or 👎 under the answers. In Phoenix
the root span gets a `user_feedback` annotation of kind HUMAN. With the API:

```powershell
# after POST /chat returns a span_id
curl -X POST http://127.0.0.1:8000/feedback -H "Content-Type: application/json" -d "{\"span_id\": \"<span_id>\", \"thumbs_up\": false, \"comment\": \"wrong number\"}"
```

You can also label answers directly in Phoenix: open a trace → Annotations → edit, and create an
annotation config called `human_correctness` (categorical: correct / incorrect).

### Lab 7 — Evaluate the evaluator

Rate at least 10 answers from an evaluated batch (thumbs in Streamlit only rate new answers, so for a
batch use `human_correctness` in the Phoenix UI). Then:

```powershell
python -m scripts.judge_agreement
```

It prints agreement and a confusion matrix, and lists every disagreement. For each one, decide who was
right. If the judge is wrong in a pattern, improve `CORRECTNESS_TEMPLATE` in `llm_evals.py`, re-run
`run_evals`, and re-check agreement. This loop is how judges are made trustworthy at work.

### Lab 8 — Watch a metric move

Set `TOP_K=1` in `.env`, run the batch and the evals again, and compare the two reports.
`retrieval_hit` and correctness should drop on multi-document questions. Put `TOP_K` back. This is a
manual preview of Phase 3, where experiments do this comparison properly.

### Lab 9 — Find the bug in a code eval

`key_facts` for q01 checks that the answer contains "20". Look at what a typical answer's Sources line
contains (`07_hr_leave_policy_2026`). Explain why q01 could pass even if the answer said 15 days, and
fix `key_facts` (hint: only check the text before "Sources:", or match whole words with a regex).
Code evals are exact, but only as good as the rule you wrote.

### Lab 10 — Write your own evaluator

The conflicting-docs questions should *mention* the conflict. Add an LLM judge called
`mentions_conflict` with `create_classifier` (copy the pattern of `answer_correctness`), run it only for
the `conflicting_docs` category, and log it like the others.

## 5. Pitfalls

- **Judges are non-deterministic.** Small score changes between runs can be noise. Look at trends and
  big differences, not ±0.05.
- **Judge failures** show as `label: error` in the run output and are not logged to Phoenix. A run with
  many errors usually means rate limits: re-run it, or use `--skip-docs` or `gpt-oss-20b`.
- **The golden dataset is code.** When a policy document changes, update the reference answers, or your
  evals will punish correct answers.
- **20 questions is small.** One question is 5% of a category score. Real eval sets have hundreds of
  questions, often built from real user questions found in traces.

## 6. How this maps to Arize AX

The concepts and the `phoenix-evals` library are the same. In Arize AX, eval results also attach to
spans (shown as eval columns and filters), and you can set up **online evals** that automatically
score a sample of live production traces. You'll build the local version of that in Phase 4.

## Done when

- [ ] You've run code-only and full evaluations and read both reports
- [ ] You can find hallucinations and "faithfully wrong" answers with a filter in Phoenix
- [ ] You've given human feedback and seen it on the trace
- [ ] You've measured judge–human agreement and investigated every disagreement
- [ ] You've fixed the q01 `key_facts` bug and written one evaluator of your own
- [ ] You can explain the difference between correctness and faithfulness, and between hit rate, MRR and precision
