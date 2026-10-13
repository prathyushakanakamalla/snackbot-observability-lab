"""HTTP API.  Run:  uvicorn api:app --reload   then open http://127.0.0.1:8000/docs"""
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from snackbot.agent import SnackBot

app = FastAPI(title="SnackBot API")
bot = SnackBot()
SESSIONS: dict[str, list[dict]] = {}  # in-memory conversation history per session


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None  # unused for now; Phase 1 attaches it to traces


class ChatResponse(BaseModel):
    answer: str
    session_id: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = SESSIONS.setdefault(session_id, [])
    result = bot.answer(req.message, history)
    history += [{"role": "user", "content": req.message}, {"role": "assistant", "content": result.answer}]
    return ChatResponse(answer=result.answer, session_id=session_id)
