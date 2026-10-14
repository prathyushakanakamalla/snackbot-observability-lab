# Phase 1 — Tracing with Arize Phoenix

**Goal:** see inside every SnackBot answer. By the end you should be able to take any wrong answer and say
*which step* went wrong (retrieval, a tool, or the LLM) in under a minute.

## 1. What changed in the code

Every Phase 1 change is marked with a `# PHASE 1` comment. Use `git diff phase-0` to see them all.

| File | Change |
|---|---|
| `snackbot/tracing.py` | **New.** Sets up OpenTelemetry → Phoenix in one call, plus small helpers for spans. |
| `snackbot/agent.py` | Wraps each answer in an **AGENT** span; attaches session, user, metadata, tags, prompt version; records errors instead of hiding them; returns `trace_id`. |
| `snackbot/tools.py` | `run_tool` creates a **TOOL** span per call (arguments in, result out, red if it failed). |
| `snackbot/retriever.py` | **RETRIEVER** span listing every chunk with its score, plus a child **EMBEDDING** span. |
| `snackbot/llm.py` | **Unchanged.** Groq calls are traced by auto-instrumentation without touching this file. |
| `snackbot/prompts.py` | `PROMPT_VERSION = "v1"`, recorded on every trace. |
| `cli.py`, `app_streamlit.py`, `api.py` | Call `setup_tracing()` at start; pass a session id and user id. |
| `scripts/run_sample_questions.py` | Tags each run so you can filter one batch in Phoenix. |
| `config.py`, `.env.example` | New settings: `TRACING`, `PHOENIX_ENDPOINT`, `PHOENIX_PROJECT`. |

## 2. Setup

```powershell
cd "D:\Agentic AI\snackbot-observability-lab"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt        # adds Phoenix + OpenInference packages
```

Add these lines to your own `.env` (they're also in `.env.example`):

```
TRACING=full
PHOENIX_ENDPOINT=http://localhost:6006
PHOENIX_PROJECT=snackbot
```

You now need **two terminals**, both with the venv activated:

```powershell
# Terminal 1: the Phoenix server. Leave it running.
phoenix serve

# Terminal 2: the app
python cli.py
```

Open **http://localhost:6006** in your browser. Phoenix stores traces in your `~/.phoenix` folder, so
they survive restarts.

## 3. The labs

Do these in order. Each one changes one thing so you can see what it adds.

### Lab 1 — Auto-instrumentation only (`TRACING=auto`)

Set `TRACING=auto` in `.env`, restart `cli.py`, and ask:

> Is CW-101 at or below its reorder point in the Dallas DC? It ships from Columbus.

In Phoenix, open the **snackbot** project. You'll see **3–4 separate traces**, each a single LLM span
named `Completions`. Click one and explore the tabs:

- **Input messages**: the exact system prompt, question, and earlier tool results sent to Groq.
- **Output**: either text or a *tool call request*, e.g. `check_inventory({"product": "CW-101", ...})`.
- **Attributes**: model name, `llm.token_count.prompt` / `completion` / `total`, invocation parameters
  (temperature), and the tool schemas sent.
- **Latency** at the top.

Questions to answer:
1. How many prompt tokens did the *first* call use vs the *last*? Why the difference?
2. Can you see what `search_documents` actually returned? (Only indirectly, inside the next call's input.)
3. If 10 people asked questions at once, how would you know which LLM calls belong together?

This is what you get "for free" with one line. Useful, but it's a pile of disconnected LLM calls.

### Lab 2 — Full tracing (`TRACING=full`)

Set `TRACING=full`, restart, ask the same question. Now there's **one trace** with a tree:

```
SnackBot.answer                AGENT       ← the whole question, start to finish
├── Completions                LLM         ← pass 1: decides to search
├── search_documents           TOOL        ← arguments the LLM chose
│   └── retrieve               RETRIEVER   ← the 4 chunks + scores
│       └── embed_query        EMBEDDING
├── Completions                LLM         ← pass 2: decides to check inventory
├── check_inventory            TOOL        ← {"on_hand": 310, "avg_daily_demand": 85}
├── Completions                LLM         ← pass 3: decides to calculate
├── calculate                  TOOL        ← "850"
└── Completions                LLM         ← pass 4: writes the answer
```

Compare it with section 8.2 of the Phase 0 walkthrough PDF. It's the same story, now recorded.

Things to find:
1. Which span took the longest? (Look at the timeline view.) Is it the LLM or retrieval?
2. Click `retrieve` → **Documents** tab. Were all 4 chunks relevant? What was the lowest score?
3. Click the AGENT span → **Attributes**: find `session.id`, `user.id`, `metadata`, `llm.prompt_template.version`.
4. Copy the `trace …` id that `cli.py` printed. In Phoenix's span filter, type
   `trace_id == "<paste>"` to jump straight to it. This is how you'd go from a user's bug report to the trace.

### Lab 3 — Find a retrieval problem

Ask: `How many unused vacation days can I carry over to next year?`

Open the trace → `retrieve` → Documents. Is `08_hr_leave_policy_2021_ARCHIVED` in the top 4? With what
score compared to the 2026 policy? Then open the final LLM span: did the answer use 5 days (2026) or
10 days (2021)? You can now separate **"retrieval brought the wrong document"** from **"the LLM picked
the wrong one"**. Without tracing, both look the same: a wrong answer.

### Lab 4 — Sessions

Run `streamlit run app_streamlit.py`. Have a 4–5 turn conversation with follow-ups ("and in Toronto?").
In Phoenix, open the **Sessions** tab. Your conversation is one session with one trace per turn.

Watch `llm.token_count.prompt` on the first LLM call of each turn. It grows every turn because the whole
history is re-sent. This is how cost creeps up in long chats.

### Lab 5 — Errors

1. In `.env` set `GROQ_MODEL=llama-9-imaginary`. Restart and ask anything. You see "Sorry, something went
   wrong". In Phoenix, the AGENT span is **red**. Click it: the status message and the **Events** tab show
   the real exception (Groq's "model not found" error) and its stack trace. Put the model back.
2. Ask: `How much CW-101 stock is in the Houston DC?` Nothing crashes, but the `check_inventory` TOOL span
   is red with `Unknown warehouse 'Houston'`. Did the LLM recover gracefully in the next LLM span?
3. In the span filter, type `status_code == 'ERROR'` to list every failure in the project.

Errors that are caught and hidden from users are the most dangerous kind in production. Tracing is how
they stop being invisible.

### Lab 6 — Batch run and filtering

```powershell
python -m scripts.run_sample_questions
```

This sends all 20 sample questions, tagged with a run tag (printed at the top of
`results/phase1_answers.md`) and their category. Try these filters in Phoenix's span search box:

| Filter | Shows |
|---|---|
| `span_kind == 'LLM'` | Only LLM calls |
| `span_kind == 'TOOL' and name == 'calculate'` | Every calculator call: were the expressions right? |
| `llm.token_count.total > 3000` | Expensive calls |
| `latency_ms > 5000` | Slow spans |
| `metadata["category"] == "conflicting_docs"` | Traces for one question category |
| `status_code == 'ERROR'` | All failures |

### Lab 7 — Root-cause your Phase 0 grades (the important one)

Take your hand-graded answers from Phase 0. For every answer that was wrong or weak, open its trace and
fill in this table. This is the core skill of AI observability.

| Question | Wrong how? | Root cause | Evidence in the trace |
|---|---|---|---|
| q07 carry-over | said 10 days | Retrieval + LLM: archived doc ranked #2, LLM used it | retrieve span: doc 08 score … |
| … | | Retrieval miss / LLM ignored context / Wrong tool or arguments / Tool returned bad data / Prompt rule not followed / Error | |

### Lab 8 — Prompt versions

In `prompts.py`, add a rule such as *"If two documents disagree, quote both and say which is newer."*
Change `PROMPT_VERSION = "v2"`. Re-run question q07 a few times. Filter by
`llm.prompt_template.version == "v2"` and compare with v1 traces. This is a manual preview of Phase 3,
where experiments do this properly over a whole dataset.

## 4. The concepts, now that you've seen them

**Trace and span.** A *span* is one timed operation with a name, start and end time, a status (UNSET, OK or
ERROR), *attributes* (key/value data) and *events* (such as exceptions). A *trace* is the tree of spans
that share a `trace_id`. Each span stores its `parent_id`; that's all it takes to draw the tree.

**Context propagation.** How does the Groq LLM span know its parent is `SnackBot.answer`? OpenTelemetry keeps
a "current span" in a context variable. `start_as_current_span` sets it; any span started inside the
`with` block reads it and becomes a child. `using_attributes(session_id=...)` works the same way: it puts
values into the context, and every span created inside picks them up, including spans made by the Groq
library that has never heard of SnackBot.

**The pipeline** that `phoenix.otel.register()` builds:

```
Tracer ──► TracerProvider ──► BatchSpanProcessor ──► OTLP HTTP exporter ──► Phoenix (localhost:6006/v1/traces)
```

`batch=True` means spans are queued and sent in the background, so tracing barely slows your app.
The trade-off is that a short script can exit before the queue is sent. That's why `cli.py` and the batch
script call `flush()` at the end.

**Auto vs manual instrumentation.** `GroqInstrumentor` (switched on by `auto_instrument=True`) patches the
Groq SDK so every `chat.completions.create` makes an LLM span automatically. Libraries can't know about
*your* logic (what an agent run is, what your tools are), so you add those spans by hand. Real systems
always use both.

**Semantic conventions (OpenInference).** Phoenix knows to draw a ranked document list because we used the
agreed attribute names: `openinference.span.kind = RETRIEVER`,
`retrieval.documents.0.document.content`, `.score`, and so on. Other examples are `input.value`,
`output.value`, `llm.token_count.prompt`, `tool.name`, `session.id` and `user.id`. Using the standard names
is what makes the UI, evals and Arize AX understand your data.

| Span kind | Used for | In SnackBot |
|---|---|---|
| AGENT | A reasoning loop that calls LLMs and tools | `SnackBot.answer` |
| LLM | One call to a language model | `Completions` (auto) |
| TOOL | A function the LLM asked to run | `search_documents`, `check_inventory`, `calculate` |
| RETRIEVER | Fetching documents | `retrieve` |
| EMBEDDING | Turning text into vectors | `embed_query` |
| CHAIN | Any other step that groups work | (not used yet) |
| RERANKER, GUARDRAIL, EVALUATOR | Reordering results, safety checks, evaluations | Phases 4–5 |

## 5. How this maps to Arize AX at work

Everything you instrumented carries over unchanged: the spans, the attribute names, sessions and the
Groq auto-instrumentation. What changes is *where the spans are sent*. With Arize AX you register with
the `arize-otel` package and your Arize space ID and API key instead of a local Phoenix endpoint:

```python
from arize.otel import register
tracer_provider = register(space_id="...", api_key="...", project_name="snackbot",
                           auto_instrument=True)
```

Then you'd see the same trace trees in the Arize AX UI. Check your team's setup at work for the exact
keys and project conventions; don't put company API keys in this lab.

## Done when

- [ ] You've seen the difference between `auto` and `full` traces for the same question
- [ ] You can find the retrieved chunks and their scores for any question
- [ ] You've found a red span caused by a hidden error and read its exception
- [ ] You've used a session view and watched prompt tokens grow
- [ ] You've filled in the Lab 7 root-cause table for at least 5 wrong answers
- [ ] You can explain context propagation in two sentences
