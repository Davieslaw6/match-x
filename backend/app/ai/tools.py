"""Tool registry. Tools are read-only except proposals; none runs code, fetches URLs or reads files. All outputs are plain JSON data."""
from datetime import date, datetime, timedelta
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from ..config import settings
from ..db import utcnow
from ..engine.dixon_coles import InsufficientData, Match, fit, rates
from ..engine.markets import grid, markets
from ..models_data import Fixture, MarketOdds, MatchResult, Team, TeamAlias
from ..providers.teams import resolve
from ..tickets import core as tk

class ResolveIn(BaseModel): query: str = Field(max_length=100)
class SearchIn(BaseModel):
    date_from: date | None = None; date_to: date | None = None; team_id: int | None = None
    home_team_id: int | None = None; away_team_id: int | None = None; status: str | None = Field(None, max_length=20)
class FormIn(BaseModel): team_id: int; n: int = Field(5, ge=1, le=20)
class H2HIn(BaseModel): team_a: int; team_b: int
class OddsIn(BaseModel): fixture_id: int
class PredIn(BaseModel): home_team_id: int; away_team_id: int
class SelIn(BaseModel): fixture: str; market: str = "1x2"; outcome: str = "home"; odds: str
class AnalyzeIn(BaseModel): selections: list[SelIn] = Field(min_length=1, max_length=30)
class ListTicketsIn(BaseModel): pass
class ProposeIn(BaseModel): ticket_id: int; operation: str = Field(max_length=20); selection_id: str | None = None
class ShotIn(BaseModel): upload_id: str = Field(max_length=64)

def _unsupported(why): return {"status": "unsupported", "reason": why}

def resolve_team(db: Session, a: ResolveIn):
    aliases = {x.alias_norm: db.get(Team, x.team_id).name for x in db.scalars(select(TeamAlias))}
    teams = list(db.scalars(select(Team))); kind, v = resolve(a.query, aliases, [t.name for t in teams])
    if kind == "match":
        t = next(t for t in teams if t.name == v); return {"status": "match", "team_id": t.id, "name": t.name}
    return {"status": "ambiguous" if kind == "ambiguous" else "none", "query": a.query, "candidates": v if kind == "ambiguous" else []}

def _name(db, i):
    t = db.get(Team, i); return t.name if t else "unknown team"

def search_fixtures(db: Session, a: SearchIn):
    q = select(Fixture).order_by(Fixture.kickoff_utc)
    if a.date_from: q = q.where(Fixture.kickoff_utc >= datetime.combine(a.date_from, datetime.min.time()))
    if a.date_to: q = q.where(Fixture.kickoff_utc < datetime.combine(a.date_to + timedelta(days=1), datetime.min.time()))
    if a.team_id: q = q.where(or_(Fixture.home_team_id == a.team_id, Fixture.away_team_id == a.team_id))
    if a.home_team_id: q = q.where(Fixture.home_team_id == a.home_team_id)
    if a.away_team_id: q = q.where(Fixture.away_team_id == a.away_team_id)
    if a.status: q = q.where(Fixture.status == a.status)
    fx = list(db.scalars(q.limit(10)))
    return {"fixtures": [{"id": f.id, "home": _name(db, f.home_team_id), "away": _name(db, f.away_team_id),
                          "kickoff_utc": f.kickoff_utc.isoformat(), "status": f.status} for f in fx]}

def _finished(db, team_id, other=None, n=None):
    q = select(Fixture, MatchResult).join(MatchResult, MatchResult.fixture_id == Fixture.id).order_by(Fixture.kickoff_utc.desc())
    if other: q = q.where(or_((Fixture.home_team_id == team_id) & (Fixture.away_team_id == other), (Fixture.home_team_id == other) & (Fixture.away_team_id == team_id)))
    else: q = q.where(or_(Fixture.home_team_id == team_id, Fixture.away_team_id == team_id))
    return list(db.execute(q.limit(n) if n else q))

def get_team_form(db: Session, a: FormIn):
    rows, ms, pts = _finished(db, a.team_id, n=a.n), [], 0
    if not rows: return {"status": "no_data", "name": _name(db, a.team_id)}
    for f, r in rows:
        home = f.home_team_id == a.team_id; gf, ga = (r.home_goals, r.away_goals) if home else (r.away_goals, r.home_goals)
        pts += 3 if gf > ga else (1 if gf == ga else 0)
        ms.append({"date": f.kickoff_utc.date().isoformat(), "opponent": _name(db, f.away_team_id if home else f.home_team_id), "gf": gf, "ga": ga})
    return {"status": "ok", "name": _name(db, a.team_id), "played": len(ms), "points": pts, "matches": ms}

def get_head_to_head(db: Session, a: H2HIn):
    rows = _finished(db, a.team_a, other=a.team_b); aw = dr = bw = 0
    for f, r in rows:
        ag, bg = (r.home_goals, r.away_goals) if f.home_team_id == a.team_a else (r.away_goals, r.home_goals)
        aw += ag > bg; bw += bg > ag; dr += ag == bg
    return {"status": "ok" if rows else "no_data", "a": _name(db, a.team_a), "b": _name(db, a.team_b), "played": len(rows), "a_wins": aw, "draws": dr, "b_wins": bw}

def get_odds(db: Session, a: OddsIn):
    obs = list(db.scalars(select(MarketOdds).where(MarketOdds.fixture_id == a.fixture_id).order_by(MarketOdds.observed_at.desc()).limit(12)))
    if not obs: return {"status": "missing", "reason": "no odds recorded for this fixture"}
    cutoff = utcnow().replace(tzinfo=None) - timedelta(minutes=settings.odds_stale_minutes)
    return {"status": "ok", "observations": [{"bookmaker": o.bookmaker, "market": o.market, "selection": o.selection,
            "odds": str(o.decimal_odds.normalize()), "observed_at": o.observed_at.isoformat(), "stale": o.observed_at < cutoff} for o in obs]}

_cache: dict = {}
def run_prediction(db: Session, a: PredIn):
    """Interim: lazily fits once per data state and caches. Replace with stored predictions + job (Phases 6/10)."""
    rows = list(db.execute(select(Fixture, MatchResult).join(MatchResult, MatchResult.fixture_id == Fixture.id)))
    key = (len(rows), max((f.kickoff_utc for f, _ in rows), default=None))
    if key not in _cache:
        ms = [Match(f.kickoff_utc, str(f.home_team_id), str(f.away_team_id), r.home_goals, r.away_goals) for f, r in rows]
        cutoff = utcnow().replace(tzinfo=None); _cache.clear(); _cache[key] = (fit(ms, cutoff), cutoff)
    f, cutoff = _cache[key]
    if isinstance(f, InsufficientData): return {"status": "insufficient_data", "reason": f.reason}
    r = rates(f, str(a.home_team_id), str(a.away_team_id))
    if isinstance(r, InsufficientData): return {"status": "insufficient_data", "reason": r.reason}
    m = markets(grid(*r, f.rho))
    return {"status": "ok", "model": "M1 Dixon-Coles", "data_cutoff": cutoff.date().isoformat(), "home": _name(db, a.home_team_id),
            "away": _name(db, a.away_team_id), "probabilities": m["1x2"], "over_2_5": m["over_under"]["2.5"]["over"], "btts_yes": m["btts"]["yes"]}

def analyze_ticket(db: Session, a: AnalyzeIn):
    from decimal import Decimal
    s = [tk.Sel(str(i), x.fixture, x.market, x.outcome, Decimal(x.odds)) for i, x in enumerate(a.selections)]
    return {"status": "ok", "combined_odds": tk.display_odds(tk.combined_odds(s)), "warnings": tk.validate(s)}

def list_tickets(db, a): return _unsupported("ticket storage is not built yet")
def propose_ticket_change(db, a): return _unsupported("ticket storage is not built yet, so no change preview exists")
def parse_screenshot(db, a): return _unsupported("screenshot import is not built yet")
class GetPredIn(BaseModel): fixture_id: int
def get_prediction(db: Session, a: GetPredIn):
    from ..predictions import latest_live
    p = latest_live(db, a.fixture_id)
    if not p: return {"status": "none", "reason": "no stored live prediction for this fixture"}
    return {"status": "ok", "model": p.model_version, "data_cutoff": p.data_cutoff_at.date().isoformat(), "probabilities": p.probabilities["1x2"]}

REGISTRY = {"resolve_team": (ResolveIn, resolve_team), "search_fixtures": (SearchIn, search_fixtures), "get_team_form": (FormIn, get_team_form),
    "get_head_to_head": (H2HIn, get_head_to_head), "get_odds": (OddsIn, get_odds), "run_prediction": (PredIn, run_prediction),
    "analyze_ticket": (AnalyzeIn, analyze_ticket), "list_tickets": (ListTicketsIn, list_tickets),
    "propose_ticket_change": (ProposeIn, propose_ticket_change), "parse_screenshot": (ShotIn, parse_screenshot), "get_prediction": (GetPredIn, get_prediction)}

def schemas(): return [{"name": n, "parameters": m.model_json_schema()} for n, (m, _) in REGISTRY.items()]
