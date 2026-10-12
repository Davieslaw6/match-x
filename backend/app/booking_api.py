from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from . import auth
from .bookings import Job, advance, create
from .db import get_db
from .models_extra import BookingCodeJob
from .models_tickets import Ticket
from .tickets_api import snapshot

class BookmakerIntegration:
    """Real integrations need authorised access and must respect the bookmaker's terms. Never scrape or ask for passwords."""
    id = "base"; supports_create = False
    def resolve_code(self, code): return None
    def search_market(self, sel): return None
    def check_availability(self, sel): return ("unsupported", None)
    def create_code(self, selections): return None
class ManualIntegration(BookmakerIntegration): id = "manual"
REGISTRY: dict = {"manual": ManualIntegration()}

router = APIRouter(prefix="/api/v1/booking-codes")
class Convert(BaseModel): ticket_id: int; bookmaker: str = Field(max_length=40)
class Confirm(BaseModel): accept_odds_changes: bool = False
def err(s, c, m): return HTTPException(s, {"code": c, "message": m})
def view(j): return {"id": j.id, "status": j.status, "reason": j.reason, "bookmaker": j.bookmaker, "per_selection": j.per_selection, "code": j.code, "confirmation_id": j.confirmation_id}

@router.post("/convert")
def convert(b: Convert, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    integ = REGISTRY.get(b.bookmaker); t = db.get(Ticket, b.ticket_id)
    if not integ: raise err(422, "unknown_bookmaker", "No integration is registered for that bookmaker.")
    if not t: raise err(404, "not_found", "Ticket not found.")
    sels = snapshot(db, t); job = Job()
    for s in ("resolved", "mapped"): advance(job, s)
    for s in sels:
        st, new = integ.check_availability(s); job.per_selection[str(s["id"])] = {"status": st, "new_odds": str(new) if new is not None else None}
    row = BookingCodeJob(ticket_id=t.id, bookmaker=b.bookmaker, status="mapped", per_selection=job.per_selection)
    if sels and all(v["status"] == "unsupported" for v in job.per_selection.values()):
        row.status = "failed"; row.reason = "No authorised integration for this bookmaker. Enter the selections manually or use the ticket export."
    else: advance(job, "previewed"); row.status = "previewed"
    db.add(row); db.commit(); return view(row)

@router.post("/{jid}/confirm")
def confirm(jid: int, b: Confirm, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    row = db.get(BookingCodeJob, jid)
    if not row: raise err(404, "not_found", "Job not found.")
    if row.status != "previewed": raise err(409, "bad_state", f"Job is {row.status}, not previewed.")
    st = [v["status"] for v in row.per_selection.values()]
    if any(x in ("unavailable", "unsupported") for x in st): raise err(409, "selections_blocked", "Some selections are unavailable or unsupported; edit the ticket first.")
    if "odds_changed" in st and not b.accept_odds_changes: raise err(409, "odds_changed", "Odds changed; confirm with accept_odds_changes to continue.")
    integ = REGISTRY[row.bookmaker]; j = Job(status="confirmed", per_selection=row.per_selection)
    sels = [dict(s) for s in snapshot(db, db.get(Ticket, row.ticket_id))]
    for s in sels:
        n = row.per_selection[str(s["id"])]["new_odds"]
        if n: s["odds"] = n
    class _Wrap:
        supports_create = integ.supports_create
        def create_code(self, s): return integ.create_code(sels)
    create(j, _Wrap(), sels); row.status, row.reason, row.code = j.status, j.reason, j.code
    if j.code: row.confirmation_id = "confirmed"
    db.commit(); return view(row)
