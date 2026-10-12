import hashlib, json, secrets
from datetime import timedelta
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import auth
from .db import get_db
from .models_tickets import IdempotencyKey, PendingChange, Ticket, TicketRevision, TicketSelection, now_naive
from .predictions import latest_live
from .tickets import core as tk
from .tickets.ops import apply, o3, to_core

router = APIRouter(prefix="/api/v1/tickets")
IDEM = Header(None, alias="Idempotency-Key", max_length=80)
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def err(status, code, msg): return HTTPException(status, {"code": code, "message": msg})

class SelIn(BaseModel):
    fixture_id: int | None = None; fixture_label: str = Field(max_length=200); market: str = Field(max_length=20); outcome: str = Field(max_length=40)
    odds: Decimal = Field(gt=1, le=10000, max_digits=9, decimal_places=3); bookmaker: str | None = Field(None, max_length=40)
class Edit(BaseModel):
    market: str | None = Field(None, max_length=20); outcome: str | None = Field(None, max_length=40); bookmaker: str | None = Field(None, max_length=40)
    odds: Decimal | None = Field(None, gt=1, le=10000, max_digits=9, decimal_places=3)
class Op(BaseModel):
    op: Literal["add", "remove", "edit", "sort", "delete_ticket"]; selection: SelIn | None = None; selection_id: int | None = None
    fields: Edit | None = None; by: Literal["odds", "fixture"] = "odds"; descending: bool = False
class NewTicket(BaseModel): name: str = Field(max_length=100); selections: list[SelIn] = Field(default_factory=list, max_length=50)
class Confirm(BaseModel): token: str = Field(max_length=100)
class SplitIn(BaseModel): parts: int = Field(2, ge=2, le=10); strategy: Literal["count", "odds", "probability"] = "count"
class OptIn(BaseModel):
    max_odds: Decimal = Field(gt=1, le=1000000, max_digits=12, decimal_places=2); max_selections: int = Field(ge=1, le=30); min_probability: float = Field(0, ge=0, le=1)

def own(db, tid):
    t = db.get(Ticket, tid)
    if not t: raise err(404, "not_found", "Ticket not found.")
    return t
def snapshot(db, t):
    rows = db.scalars(select(TicketSelection).where(TicketSelection.ticket_id == t.id).order_by(TicketSelection.position, TicketSelection.id))
    return [{"id": r.id, "fixture_id": r.fixture_id, "fixture_label": r.fixture_label, "market": r.market, "outcome": r.outcome, "odds": o3(r.odds), "bookmaker": r.bookmaker} for r in rows]
def write(db, t, sels):
    db.query(TicketSelection).filter_by(ticket_id=t.id).delete()
    for i, s in enumerate(sels): db.add(TicketSelection(ticket_id=t.id, position=i, fixture_id=s.get("fixture_id"), fixture_label=s["fixture_label"], market=s["market"], outcome=s["outcome"], odds=Decimal(s["odds"]), bookmaker=s.get("bookmaker")))
def probs(db, sels):
    out = {}
    for i, s in enumerate(sels):
        p = latest_live(db, s["fixture_id"]) if s.get("fixture_id") else None
        if p and s["market"] == "1x2" and s["outcome"] in ("home", "draw", "away"): out[i] = p.probabilities["1x2"][s["outcome"]]
    return out
def combined(sels): return tk.display_odds(tk.combined_odds(to_core(sels))) if sels else None
def out(db, t):
    s = snapshot(db, t); return {"id": t.id, "name": t.name, "status": t.status, "selections": s, "combined_odds": combined(s), "warnings": tk.validate(to_core(s))}

def idempotent(db, key, route, body, fn):
    if not key: return fn()
    bh = sha(json.dumps(body, sort_keys=True, default=str)); row = db.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.route == route))
    if row:
        if row.body_hash != bh: raise err(422, "idempotency_conflict", "This Idempotency-Key was used with a different request.")
        return row.response
    resp = fn(); db.add(IdempotencyKey(key=key, route=route, body_hash=bh, response=resp)); db.commit(); return resp

def pend(db, kind, tid, payload, base):
    tok = secrets.token_urlsafe(24)
    db.add(PendingChange(token_hash=sha(tok), kind=kind, ticket_id=tid, payload=payload, base_hash=sha(json.dumps(base, sort_keys=True)), expires_at=now_naive() + timedelta(minutes=10))); db.commit(); return tok

@router.post("")
def create(b: NewTicket, key: str | None = IDEM, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    def go():
        t = Ticket(name=b.name); db.add(t); db.flush(); sels = [{**s.model_dump(), "odds": o3(s.odds)} for s in b.selections]; write(db, t, sels)
        db.add(TicketRevision(ticket_id=t.id, before=[], after=sels, actor="owner", note="created")); db.commit(); return out(db, t)
    return idempotent(db, key, "create", b.model_dump(mode="json"), go)

@router.get("")
def list_(_=Depends(auth.current_session), db: Session = Depends(get_db)): return {"items": [out(db, t) for t in db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(100))]}
@router.get("/{tid}")
def get(tid: int, _=Depends(auth.current_session), db: Session = Depends(get_db)): return out(db, own(db, tid))
@router.get("/{tid}/revisions")
def revisions(tid: int, _=Depends(auth.current_session), db: Session = Depends(get_db)):
    own(db, tid); return {"items": [{"id": r.id, "before": r.before, "after": r.after, "actor": r.actor, "note": r.note, "at": r.created_at.isoformat() + "Z"} for r in db.scalars(select(TicketRevision).where(TicketRevision.ticket_id == tid).order_by(TicketRevision.id))]}

@router.post("/{tid}/changes")
def preview(tid: int, b: Op, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = own(db, tid); before = snapshot(db, t)
    if b.op == "delete_ticket":
        return {"before": before, "after": [], "warnings": ["This deletes the ticket and its revision history."], "confirmation_token": pend(db, "delete", tid, {}, before)}
    try: after = apply(before, b.model_dump(mode="json", exclude_none=True) | ({"selection": {**b.selection.model_dump(mode="json")}} if b.selection else {}))
    except KeyError as e: raise err(404, "selection_not_found", str(e).strip("'\""))
    return {"before": before, "after": after, "combined_odds_before": combined(before), "combined_odds_after": combined(after),
            "warnings": tk.validate(to_core(after)), "confirmation_token": pend(db, "edit", tid, {"after": after}, before)}

@router.post("/{tid}/changes/confirm")
def confirm(tid: int, b: Confirm, key: str | None = IDEM, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = own(db, tid)
    def go():
        pc = db.scalar(select(PendingChange).where(PendingChange.token_hash == sha(b.token), PendingChange.ticket_id == tid))
        if not pc or pc.expires_at < now_naive(): raise err(404, "invalid_token", "Confirmation token is invalid or expired.")
        before = snapshot(db, t)
        if sha(json.dumps(before, sort_keys=True)) != pc.base_hash: raise err(409, "ticket_changed", "The ticket changed since the preview; request a new preview.")
        if pc.kind == "delete": db.delete(pc); db.query(TicketSelection).filter_by(ticket_id=tid).delete(); db.delete(t); db.commit(); return {"deleted": tid}
        if pc.kind == "edit":
            write(db, t, pc.payload["after"]); db.add(TicketRevision(ticket_id=tid, before=before, after=pc.payload["after"], actor="owner", note="edit"))
            db.delete(pc); db.commit(); return out(db, t)
        ids = []
        for i, part in enumerate(pc.payload["parts"], 1):
            n = Ticket(name=f"{t.name} (part {i})"); db.add(n); db.flush(); write(db, n, part); ids.append(n.id)
            db.add(TicketRevision(ticket_id=n.id, before=[], after=part, actor="owner", note=f"split from {tid}"))
        db.add(TicketRevision(ticket_id=tid, before=before, after={"split_into": ids}, actor="owner", note="split"))
        db.delete(pc); db.commit(); return {"created": ids}
    return idempotent(db, key, f"{tid}:confirm", b.model_dump(), go)

@router.post("/{tid}/duplicate")
def duplicate(tid: int, key: str | None = IDEM, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = own(db, tid)
    def go():
        n = Ticket(name=f"{t.name} (copy)"); db.add(n); db.flush(); s = snapshot(db, t); write(db, n, s)
        db.add(TicketRevision(ticket_id=n.id, before=[], after=s, actor="owner", note=f"duplicate of {tid}")); db.commit(); return out(db, n)
    return idempotent(db, key, f"{tid}:duplicate", {}, go)

@router.post("/{tid}/split")
def split(tid: int, b: SplitIn, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = own(db, tid); s = snapshot(db, t)
    if len(s) < b.parts: raise err(422, "too_few_selections", "Fewer selections than parts.")
    pr = probs(db, s); core = to_core(s, pr)
    parts = tk.split(core, b.parts, b.strategy); byid = {str(x["id"]): x for x in s}
    plist = [[byid[c.id] for c in p] for p in parts]
    return {"parts": [{"selections": p, "combined_odds": combined(p)} for p in plist], "confirmation_token": pend(db, "split", tid, {"parts": plist}, s)}

@router.get("/{tid}/analysis")
def analysis(tid: int, _=Depends(auth.current_session), db: Session = Depends(get_db)):
    t = own(db, tid); s = snapshot(db, t); pr = probs(db, s)
    return {**out(db, t), "model_probabilities": {str(s[i]["id"]): round(p, 4) for i, p in pr.items()},
            "caveat": "Combined odds multiply selection prices. A joint probability is not shown because selections may be correlated and independence cannot be assumed."}

@router.post("/{tid}/optimise")
def optimise(tid: int, b: OptIn, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = own(db, tid); s = snapshot(db, t); pr = probs(db, s); core = to_core(s, pr)
    kept, removed = tk.optimise(core, b.max_odds, b.max_selections, b.min_probability)
    return {"keep": [int(k.id) for k in kept], "remove": [{"selection_id": int(r.id), "reason": why} for r, why in removed],
            "combined_odds_if_applied": combined([x for x in s if str(x["id"]) in {k.id for k in kept}]), "applied": False,
            "note": "Suggestions only. Apply removals through the change preview and confirm flow."}

@router.get("/{tid}/export")
def export(tid: int, format: Literal["csv", "json", "text"] = Query("json"), _=Depends(auth.current_session), db: Session = Depends(get_db)):
    t = own(db, tid); o = out(db, t)
    if format == "json": return o
    if format == "csv": return PlainTextResponse(tk.export_csv(to_core(o["selections"])), media_type="text/csv")
    lines = [f"Ticket: {t.name}"] + [f"{i}. {x['fixture_label']} - {x['market']} {x['outcome']} @ {x['odds']}" for i, x in enumerate(o["selections"], 1)]
    return PlainTextResponse("\n".join(lines + [f"Combined odds: {o['combined_odds']}", "Estimates and prices only; no outcome is guaranteed."]))
