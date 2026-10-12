from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased
from . import auth, predictions
from .ai.tools import FormIn, H2HIn, _finished, get_head_to_head, get_team_form
from .config import settings
from .db import get_db, utcnow
from .engine.dixon_coles import InsufficientData
from .models_data import Competition, Fixture, MarketOdds, Team
from .models_pred import Prediction
from .odds import analysis as oa
from .providers.teams import normalise

router = APIRouter()
STATUSES = {"scheduled", "live", "finished", "postponed", "abandoned", "cancelled"}
def local(dt: datetime) -> str: return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).isoformat()
def nf(msg, code="not_found", status=404): return HTTPException(status, {"code": code, "message": msg})

@router.get("/api/v1/competitions")
def competitions(_=Depends(auth.current_session), db: Session = Depends(get_db)):
    return {"items": [{"code": c.code, "name": c.name} for c in db.scalars(select(Competition).where(Competition.enabled).order_by(Competition.name))]}

class Fav(BaseModel): value: bool
@router.put("/api/v1/teams/{team_id}/favourite")
def favourite(team_id: int, b: Fav, _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    t = db.get(Team, team_id)
    if not t: raise nf("Team not found.")
    t.favourite = b.value; db.commit(); return {"team_id": t.id, "favourite": t.favourite}

@router.get("/api/v1/fixtures")
def list_fixtures(date_from: date | None = None, date_to: date | None = None, competition: str | None = Query(None, max_length=20),
                  q: str | None = Query(None, max_length=60), status: str | None = None, favourites_only: bool = False,
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), _=Depends(auth.current_session), db: Session = Depends(get_db)):
    if status and status not in STATUSES: raise nf("Unknown status.", "invalid_status", 422)
    H, A = aliased(Team), aliased(Team)
    base = select(Fixture, Competition.code, H, A).join(Competition, Competition.id == Fixture.competition_id).join(H, H.id == Fixture.home_team_id).join(A, A.id == Fixture.away_team_id)
    if date_from: base = base.where(Fixture.kickoff_utc >= datetime.combine(date_from, datetime.min.time()))
    if date_to: base = base.where(Fixture.kickoff_utc < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if competition: base = base.where(Competition.code == competition)
    if status: base = base.where(Fixture.status == status)
    if q: base = base.where(or_(H.norm.contains(normalise(q)), A.norm.contains(normalise(q))))
    if favourites_only: base = base.where(or_(H.favourite, A.favourite))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.execute(base.order_by(Fixture.kickoff_utc, Fixture.id).limit(page_size).offset((page - 1) * page_size)).all()
    have = set(db.scalars(select(Prediction.fixture_id).where(Prediction.kind == "live", Prediction.fixture_id.in_([r[0].id for r in rows]))))
    return {"page": page, "page_size": page_size, "total": total, "items": [{"id": f.id, "competition": code, "home": h.name, "away": a.name,
            "kickoff_utc": f.kickoff_utc.isoformat() + "Z", "kickoff_local": local(f.kickoff_utc), "timezone": settings.timezone,
            "status": f.status, "prediction_available": f.id in have} for f, code, h, a in rows]}

def _split(db, team_id, home, n=10):
    rows = [(f, r) for f, r in _finished(db, team_id) if (f.home_team_id == team_id) == home][:n]
    if not rows: return None
    gf = sum((r.home_goals if home else r.away_goals) for _, r in rows); ga = sum((r.away_goals if home else r.home_goals) for _, r in rows)
    return {"played": len(rows), "goals_for_avg": round(gf / len(rows), 2), "goals_against_avg": round(ga / len(rows), 2)}

@router.get("/api/v1/fixtures/{fid}")
def fixture_detail(fid: int, _=Depends(auth.current_session), db: Session = Depends(get_db)):
    f = db.get(Fixture, fid)
    if not f: raise nf("Fixture not found.")
    return {"id": f.id, "home": db.get(Team, f.home_team_id).name, "away": db.get(Team, f.away_team_id).name, "status": f.status,
            "kickoff_utc": f.kickoff_utc.isoformat() + "Z", "kickoff_local": local(f.kickoff_utc), "timezone": settings.timezone}

class PredIn(BaseModel): force: bool = False
@router.post("/api/v1/fixtures/{fid}/predictions")
def make_prediction(fid: int, b: PredIn = PredIn(), _=Depends(auth.require_csrf), db: Session = Depends(get_db)):
    f = db.get(Fixture, fid)
    if not f: raise nf("Fixture not found.")
    try: res = predictions.generate(db, f, force=b.force)
    except predictions.TooLate as e: raise nf(str(e), "too_late", 409)
    if isinstance(res, InsufficientData): return {"prediction": None, "insufficient_data": res.reason}
    p, reused = res; return {"prediction": _pred(p), "reused": reused}

def _pred(p): return {"id": p.id, "kind": p.kind, "model_version": p.model_version, "data_cutoff_at": p.data_cutoff_at.isoformat() + "Z",
                      "created_at": p.created_at.isoformat() + "Z", "supersedes_id": p.supersedes_id, "probabilities": p.probabilities, "features": p.features}

@router.get("/api/v1/fixtures/{fid}/analysis")
def analysis(fid: int, n: int = Query(5, ge=1, le=20), _=Depends(auth.current_session), db: Session = Depends(get_db)):
    f = db.get(Fixture, fid)
    if not f: raise nf("Fixture not found.")
    now = utcnow().replace(tzinfo=None); warn = []
    h, a = db.get(Team, f.home_team_id), db.get(Team, f.away_team_id)
    out = {"fixture": fixture_detail(fid, None, db), "form": {"home": get_team_form(db, FormIn(team_id=h.id, n=n)), "away": get_team_form(db, FormIn(team_id=a.id, n=n))},
           "splits": {"home_team_at_home": _split(db, h.id, True), "away_team_away": _split(db, a.id, False)},
           "head_to_head": get_head_to_head(db, H2HIn(team_a=h.id, team_b=a.id)),
           "expected_goals": {"status": "unavailable", "reason": "the configured data provider does not supply xG"},
           "injuries": {"status": "unavailable", "reason": "the configured data provider does not supply injuries or suspensions"}}
    for side, t in (("home", h), ("away", a)):
        if out["form"][side]["status"] != "ok": warn.append(f"No finished matches on record for {t.name}.")
    warn += ["Expected goals are unavailable for this provider.", "Injuries and suspensions are unavailable for this provider."]
    pred = predictions.latest_live(db, f.id)
    out["prediction"] = _pred(pred) if pred else None
    if not pred: warn.append("No stored prediction for this fixture yet.")
    else:
        ft = pred.features
        out["explanation"] = (f"Model {pred.model_version} estimates expected goals of {ft['home_xg']:.2f} for {h.name} and {ft['away_xg']:.2f} for {a.name}, "
            f"fitted on {ft['training_matches']} past matches in this competition up to {pred.data_cutoff_at.date().isoformat()}. "
            "It uses only past scores, so it cannot see injuries, lineups or motivation.")
    obs = list(db.scalars(select(MarketOdds).where(MarketOdds.fixture_id == f.id)))
    best = oa.latest_complete_1x2(obs); out["odds"] = None
    if not best: warn.append("No complete 1X2 odds recorded for this fixture.")
    else:
        bk, odds, when = best; stale = oa.is_stale(when, f.kickoff_utc, now)
        if stale: warn.append("Odds are stale for this point before kickoff; check the bookmaker.")
        valid = pred is not None and pred.kickoff_utc == f.kickoff_utc and f.status == "scheduled"
        out["odds"] = {"bookmaker": bk, "observed_at": when.isoformat() + "Z", "stale": stale, "stale_after_minutes": oa.stale_minutes((f.kickoff_utc - now).total_seconds() / 60),
                       "comparison": oa.compare(odds, pred.probabilities["1x2"] if valid else None, fresh=not stale and valid)}
    out["warnings"] = warn; out["notice"] = "Statistical estimates, not advice or guarantees."
    return out
