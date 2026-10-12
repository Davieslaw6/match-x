from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from . import auth, screenshots as sc
from .db import get_db
from .models_extra import UploadedFile
from .models_tickets import Ticket, TicketRevision
from .tickets_api import SelIn, out, o3, write

router = APIRouter(prefix="/api/v1/tickets/import-image")
def err(s, c, m): return HTTPException(s, {"code": c, "message": m})

@router.post("")
async def upload(file: UploadFile = File(...), _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    ex = sc.get_extractor()
    if ex is None: raise err(503, "vision_unconfigured", "No vision extractor is configured.")
    data = await file.read(sc.MAX_BYTES + 1)
    try: rec = sc.store(db, data)
    except ValueError as e: raise err(422, "invalid_image", str(e))
    try: slip = sc.Slip.model_validate(ex.extract(data))  # extractor output is untrusted data, validated, never executed
    except Exception: raise err(422, "extraction_invalid", "The extracted data failed validation.")
    return {"upload_id": rec.id, **sc.match(db, slip), "notice": "Review required. Nothing becomes a ticket until you confirm."}

class Confirm(BaseModel): upload_id: int; name: str = Field(max_length=100); entries: list[SelIn] = Field(min_length=1, max_length=30)
@router.post("/confirm")
def confirm(b: Confirm, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    if not db.get(UploadedFile, b.upload_id): raise err(404, "not_found", "Upload not found.")
    t = Ticket(name=b.name); db.add(t); db.flush(); sels = [{**s.model_dump(), "odds": o3(s.odds)} for s in b.entries]; write(db, t, sels)
    db.add(TicketRevision(ticket_id=t.id, before=[], after=sels, actor="owner", note=f"screenshot import {b.upload_id}")); db.commit(); return out(db, t)
