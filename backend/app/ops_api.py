from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import numpy as np
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased
from . import auth, jobs
from .config import settings
from .db import get_db
from .engine.metrics import calibration, sharpness
from .models_chat import Conversation, Message
from .models_data import DataSyncRun, Fixture, Team
from .models_extra import AppSetting, BookingCodeJob, PredictionEvaluation, UploadedFile
from .models_pred import Prediction
from .models_tickets import IdempotencyKey, PendingChange, Ticket, TicketRevision, TicketSelection, now_naive
from .tickets_api import err, pend, sha

router = APIRouter(prefix="/api/v1")

@router.get("/prediction-history")
def history(kind: Literal["live", "backtest"] | None = None, state: Literal["resolved", "unresolved"] | None = None,
            page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), _=Depends(auth.current_session), db: Session = Depends(get_db)):
    H, A = aliased(Team), aliased(Team)
    q = (select(Prediction, PredictionEvaluation, Fixture, H.name, A.name).join(Fixture, Fixture.id == Prediction.fixture_id)
         .join(H, H.id == Fixture.home_team_id).join(A, A.id == Fixture.away_team_id).outerjoin(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id))
    if kind: q = q.where(Prediction.kind == kind)
    if state == "resolved": q = q.where(PredictionEvaluation.id.is_not(None))
    if state == "unresolved": q = q.where(PredictionEvaluation.id.is_(None))
    rows = db.execute(q.order_by(Prediction.id.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    counts = {f"{k}_{'resolved' if r else 'unresolved'}": n for k, r, n in db.execute(
        select(Prediction.kind, PredictionEvaluation.id.is_not(None), func.count()).outerjoin(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id).group_by(Prediction.kind, PredictionEvaluation.id.is_not(None)))}
    return {"counts": counts, "items": [{"id": p.id, "kind": p.kind, "fixture": f"{h} vs {a}", "kickoff_utc": f.kickoff_utc.isoformat() + "Z", "model_version": p.model_version,
            "probabilities_1x2": p.probabilities["1x2"], "data_cutoff_at": p.data_cutoff_at.isoformat() + "Z", "resolved": e is not None,
            "evaluation": None if e is None else {"outcome": ["home", "draw", "away"][e.outcome], "log_loss": e.log_loss, "brier": e.brier, "rps": e.rps}} for p, e, f, h, a in rows]}

@router.get("/prediction-history/calibration")
def calib(_=Depends(auth.current_session), db: Session = Depends(get_db)):
    rows = db.execute(select(Prediction, PredictionEvaluation).join(PredictionEvaluation, PredictionEvaluation.prediction_id == Prediction.id).where(Prediction.kind == "live")).all()
    if not rows: return {"n": 0, "message": "No resolved live predictions yet."}
    P = np.array([[p.probabilities["1x2"][k] for k in ("home", "draw", "away")] for p, _ in rows]); y = np.array([e.outcome for _, e in rows]); table, ece = calibration(P, y, 5)
    return {"n": len(rows), "kind": "live", "mean_log_loss": float(np.mean([e.log_loss for _, e in rows])), "sharpness": sharpness(P), "ece": ece,
            "reliability": [{"mean_predicted": a, "observed": b, "n": n} for a, b, n in table], "insufficient_sample": len(rows) < 30}

DEFAULTS = lambda: {"timezone": settings.timezone, "odds_format": "decimal", "retention_days": "365"}
class SettingsIn(BaseModel):
    timezone: str | None = Field(None, max_length=60); odds_format: Literal["decimal", "fractional", "american"] | None = None; retention_days: int | None = Field(None, ge=30, le=3650)
@router.get("/settings")
def get_settings(_=Depends(auth.current_session), db: Session = Depends(get_db)):
    return {**DEFAULTS(), **{r.key: r.value for r in db.scalars(select(AppSetting))}}
@router.put("/settings")
def put_settings(b: SettingsIn, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    if b.timezone:
        try: ZoneInfo(b.timezone)
        except (ZoneInfoNotFoundError, ValueError): raise err(422, "invalid_timezone", "Unknown IANA timezone.")
    for k, v in b.model_dump(exclude_none=True).items():
        row = db.get(AppSetting, k)
        if row: row.value = str(v)
        else: db.add(AppSetting(key=k, value=str(v)))
    db.commit(); return get_settings(None, db)

class Tok(BaseModel): token: str = Field(max_length=100); phrase: str | None = None
def take(db, kind, tok):
    pc = db.scalar(select(PendingChange).where(PendingChange.token_hash == sha(tok), PendingChange.kind == kind))
    if not pc or pc.expires_at < now_naive(): raise err(404, "invalid_token", "Confirmation token is invalid or expired.")
    db.delete(pc); db.commit()
@router.post("/data/export/request")
def export_req(_=Depends(auth.require_csrf), db: Session = Depends(get_db)): return {"confirmation_token": pend(db, "export", None, {}, []), "note": "Confirm to download your data as JSON."}
@router.post("/data/export/confirm")
def export_go(b: Tok, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    take(db, "export", b.token); dump = lambda m: [{c.name: (str(getattr(r, c.name)) if not isinstance(getattr(r, c.name), (int, float, str, type(None), dict, list)) else getattr(r, c.name)) for c in m.__table__.columns} for r in db.scalars(select(m))]
    return {k: dump(m) for k, m in {"tickets": Ticket, "ticket_selections": TicketSelection, "ticket_revisions": TicketRevision, "conversations": Conversation, "messages": Message, "settings": AppSetting, "predictions": Prediction}.items()}
@router.post("/data/delete/request")
def delete_req(_=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    return {"confirmation_token": pend(db, "delete_all", None, {}, []), "required_phrase": "DELETE MY DATA", "warning": "Deletes tickets, revisions, conversations, uploads and settings. Provider data and stored predictions are kept."}
@router.post("/data/delete/confirm")
def delete_go(b: Tok, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    if b.phrase != "DELETE MY DATA": raise err(422, "phrase_required", "Type the confirmation phrase exactly.")
    take(db, "delete_all", b.token); counts = {}
    for m in (BookingCodeJob, TicketRevision, TicketSelection, Ticket, Message, Conversation, AppSetting, IdempotencyKey, UploadedFile): counts[m.__tablename__] = db.query(m).delete()
    db.commit(); return {"deleted": counts}

@router.post("/jobs/{name}/run")
def run(name: str, _=Depends(auth.require_csrf)):
    if name not in jobs.JOBS: raise err(404, "unknown_job", "Unknown job.")
    return jobs.run_job(name)
@router.get("/jobs/status")
def status(_=Depends(auth.current_session), db: Session = Depends(get_db)):
    return {"items": [{"job": r.job, "status": r.status, "started_at": r.started_at.isoformat() + "Z", "error": r.error_summary} for r in db.scalars(select(DataSyncRun).order_by(DataSyncRun.id.desc()).limit(20))]}
