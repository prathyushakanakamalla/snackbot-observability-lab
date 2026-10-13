# Phase 0 — Flying Blind

**Goal:** get SnackBot running, use it, and notice how little you can see when something goes wrong.
Every question you can't answer below is something an observability tool will answer in a later phase.

## 1. Get it running (about 15 minutes)

Follow the setup in `README.md`, then run `python cli.py` and ask:

1. `How many PTO days does a new full-time employee get per year?`
2. `How many cases of DipCo French Onion Dip are in the Dallas DC?`
3. `Is CW-101 at or below its reorder point in the Dallas DC? It ships from Columbus.`

Question 3 needs several steps: search the supply-chain policy for the formula and lead time, check
inventory, then calculate. Did it get it right? (Work it out yourself from the docs and
`data/inventory.json`.) **How do you know which steps it actually took?**

## 2. Run the sample set

```powershell
python -m scripts.run_sample_questions
```

Open `results/phase0_answers.md` and grade each answer by hand: correct, partly correct, wrong, or
"said I don't know". Keep your grades. In Phase 2 you'll compare them with automatic evaluations.

## 3. Questions to try answering (you mostly can't, yet)

For each wrong or weak answer, try to work out:

- **Retrieval:** Which chunks did the search return? Was the right document even in the top 4?
- **Reasoning:** Did the LLM see the right information and ignore it, or never see it?
- **Tools:** Which tools ran, in what order, with what arguments? What did each return?
- **Errors:** When it said "Sorry, something went wrong", what actually broke? A rate limit? A
  malformed tool call? (Look at `agent.py`: the error is swallowed.)
- **Cost and speed:** How many tokens did that question use? Which step was slow?
- **Conversations:** In the Streamlit app, after a 5-turn chat, how big is the prompt now?
- **Drift:** If you change `TOP_K` or `CHUNK_SIZE` in `.env` (re-run ingest after changing chunk
  settings), are answers better or worse overall? How would you prove it?

The only tool you have right now is `print()`. Try adding a few prints to `agent.py` to see what
it's like. That is "logging", and you'll see in Phase 1 why tracing is much more than that.

## 4. Things planted in the data (spoilers — try to find them first)

<details>
<summary>Click to reveal</summary>

- **Outdated document:** `08_hr_leave_policy_2021_ARCHIVED.md` contradicts the current 2026 HR policy
  (15 vs 20 PTO days, 10 vs 5 carry-over days). The title doesn't say "archived", only the file name.
- **Conflicting numbers:** Refrigerated receiving limit is 4 °C in the food-safety SOP but 5 °C in the
  older warehouse handbook.
- **Data-quality bug:** Sol Verde Zesty Lime's list price is $43.20 in the catalog but $45.00 in the
  Q4 promotions doc.
- **Indirect prompt injection:** The supplier bulletin contains a fake "SYSTEM NOTICE TO AI
  ASSISTANTS". Question q17 can pull it into the prompt.
- **Out of stock:** Zesty Lime has 0 cases in Toronto, so "days of stock" is 0.
- **Discontinued product:** Jalapeño Kick (CW-105) still has a little stock but can't be ordered.
- **Not in docs:** There is no dress-code policy. A good answer says "I don't know".

</details>

## 5. Vocabulary to have ready for Phase 1

- **Trace**: the full record of one request, from question to answer.
- **Span**: one step inside a trace (an LLM call, a retrieval, a tool call), with start/end time,
  inputs, outputs and attributes.
- **Span kinds** (OpenInference): CHAIN, LLM, RETRIEVER, TOOL, AGENT, EMBEDDING, RERANKER, GUARDRAIL, EVALUATOR.
- **Session**: several traces that belong to one conversation.
- **Instrumentation**: code that creates spans. *Auto*-instrumentation wraps libraries (like the Groq
  SDK) for you; *manual* instrumentation is spans you add yourself.
- **OpenTelemetry (OTel)**: the open standard for sending traces. **OpenInference** is Arize's set of
  conventions on top of OTel for AI apps. Phoenix (local, open source) and Arize AX (enterprise) both
  read it, which is why the instrumentation you write in Phase 1 carries over to work.

## Done when

- [ ] All three entry points run (CLI, Streamlit, API)
- [ ] You've hand-graded the 20 sample answers
- [ ] You've found at least 3 of the planted problems from SnackBot's answers alone
- [ ] You can name 3 things you wanted to see but couldn't
