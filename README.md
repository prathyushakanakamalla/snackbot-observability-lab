# SnackBot — AI Observability Lab

A hands-on project for learning AI observability end to end: tracing, evaluation, experiments,
monitoring and debugging. SnackBot is an internal assistant for **Crunchwell Foods**, a fictional snack
and beverage company. It answers questions from 15 internal documents and can check live inventory.

We build it in phases. **Phase 0 (this version) has no observability at all**, on purpose.

| Phase | What you add | What you learn |
|---|---|---|
| **0 — Baseline** ✅ | The app itself | What it feels like to debug an LLM app blind |
| 1 — Tracing | Arize Phoenix + OpenTelemetry/OpenInference | Read trace trees, spans, tokens, latency, sessions |
| 2 — Evaluation | Golden dataset, code evals, LLM-as-judge, feedback | Measure quality instead of eyeballing it |
| 3 — Experiments | Compare prompts, models, chunk size, top-k | Prove a change is better |
| 4 — Monitoring | Online evals, dashboards, prompt versions, guardrails | Run it like production |
| 5 — Break & fix | Hidden bugs to find using only traces/evals | Real debugging skill |
| 6 — Arize AX | Same app on the enterprise platform | What changes at work |

## How SnackBot works

```
 user question
      │
      ▼
 ┌──────────── agent loop (snackbot/agent.py) ────────────┐
 │  Groq LLM decides ──► tool call? ──yes──► run tool ─┐  │
 │        ▲                  │                         │  │
 │        └──── tool result ◄┼─────────────────────────┘  │
 │                           no                           │
 └───────────────────────────┼────────────────────────────┘
                             ▼
                        final answer

 tools (snackbot/tools.py)
   search_documents  → retriever.py → embeddings (local) → data/index/
   check_inventory   → data/inventory.json
   calculate         → safe arithmetic
```

| File | Role |
|---|---|
| `snackbot/config.py` | All settings (model, chunk size, top-k…). Read from `.env`. |
| `snackbot/ingest.py` | Docs → chunks (split on `##` headings, then ~800-char windows) → embeddings → `data/index/` |
| `snackbot/embeddings.py` | Local `all-MiniLM-L6-v2` embeddings (free, no API) |
| `snackbot/retriever.py` | Cosine-similarity search with plain numpy |
| `snackbot/tools.py` | Tool schemas the LLM sees + Python implementations |
| `snackbot/prompts.py` | System prompt |
| `snackbot/llm.py` | Groq client with retries for rate limits |
| `snackbot/agent.py` | The tool-calling loop |
| `cli.py` / `app_streamlit.py` / `api.py` | Three ways to talk to it: terminal, web UI, HTTP |
| `data/docs/` | The 15 knowledge-base documents |
| `data/sample_questions.json` | 20 test questions across categories (becomes the eval dataset in Phase 2) |

## Setup (Windows, PowerShell)

You need Python 3.10 or newer and a free Groq API key from https://console.groq.com/keys.

```powershell
cd "D:\Agentic AI\snackbot-observability-lab"

python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

pip install -r requirements.txt

copy .env.example .env
notepad .env          # paste your Groq key into GROQ_API_KEY

python -m snackbot.ingest   # builds the vector index (first run downloads a ~90 MB embedding model)
```

## Run it

```powershell
python cli.py                          # chat in the terminal
streamlit run app_streamlit.py         # web chat at http://localhost:8501
uvicorn api:app --reload               # API; try it at http://127.0.0.1:8000/docs
python -m scripts.run_sample_questions # runs all 20 sample questions → results/phase0_answers.md
```

## Groq free tier

The default model is `llama-3.3-70b-versatile`. On the free tier it allows about 30 requests a minute,
1,000 requests a day, and 12,000 tokens a minute. One SnackBot question uses 2–4 LLM calls, so the
sample-question script pauses between questions. To try another model, change `GROQ_MODEL` in `.env`
(for example `llama-3.1-8b-instant` or `openai/gpt-oss-120b`). Limits change, so check
https://console.groq.com/settings/limits for your account.

## Next

Work through `learning_notes/00_phase0_baseline.md`, then tell Claude you're ready for Phase 1.
