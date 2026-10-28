"""HTTP API.  Run:  uvicorn api:app --reload   then open http://127.0.0.1:8000/docs"""
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from snackbot.agent import SnackBot
from snackbot.feedback import log_feedback
from snackbot.tracing import setup_tracing

setup_tracing()  # PHASE 1
app = FastAPI(title="SnackBot API")
bot = SnackBot()
SESSIONS: dict[str, list[dict]] = {}  # in-memory conversation history per session


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    trace_id: str | None = None  # PHASE 1: return it so a bug report can point at the exact trace
    span_id: str | None = None


class FeedbackRequest(BaseModel):  # PHASE 2
    span_id: str            # the span_id returned by /chat
    thumbs_up: bool
    comment: str | None = None
    user_id: str | None = None


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    """PHASE 2: a front end calls this when the user rates an answer."""
    ok = log_feedback(req.span_id, req.thumbs_up, req.comment, req.user_id)
    return {"logged": ok}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = SESSIONS.setdefault(session_id, [])
    result = bot.answer(req.message, history, session_id=session_id, user_id=req.user_id,
                        metadata={"interface": "api"})
    history += [{"role": "user", "content": req.message}, {"role": "assistant", "content": result.answer}]
    return ChatResponse(answer=result.answer, session_id=session_id,
                        trace_id=result.trace_id, span_id=result.span_id)
