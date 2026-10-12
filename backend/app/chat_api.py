import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import auth
from .ai.llm import make_llm
from .ai.orchestrator import chat
from .config import settings
from .db import SessionLocal, get_db
from .models_chat import Conversation, Message

router = APIRouter()
class ChatIn(BaseModel): message: str = Field(min_length=1, max_length=2000); conversation_id: int | None = None

@router.post("/api/v1/chat")
async def chat_route(b: ChatIn, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    llm = make_llm(settings)
    if llm is None: raise HTTPException(503, {"code": "llm_unconfigured", "message": "No language model is configured. Set LLM_PROVIDER."})
    conv = db.get(Conversation, b.conversation_id) if b.conversation_id else None
    if b.conversation_id and conv is None: raise HTTPException(404, {"code": "not_found", "message": "Conversation not found."})
    if conv is None: conv = Conversation(); db.add(conv); db.flush()
    prior = [{"role": m.role, "content": m.content} for m in db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id))]
    db.add(Message(conversation_id=conv.id, role="user", content=b.message)); db.commit(); cid = conv.id

    async def stream():
        sse = lambda ev, d: f"event: {ev}\ndata: {json.dumps(d, default=str)}\n\n"
        yield sse("start", {"conversation_id": cid, "llm": settings.llm_provider})
        with SessionLocal() as s:
            async for e in chat(llm, s, prior, b.message):
                yield sse(e["type"], e)
                if e["type"] in ("final", "error"):
                    s.add(Message(conversation_id=cid, role="assistant", content=e["text"])); s.commit()
        yield sse("done", {})
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
