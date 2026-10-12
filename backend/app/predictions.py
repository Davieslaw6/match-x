from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import utcnow
from .engine.dixon_coles import InsufficientData, Match, fit, rates
from .engine.markets import correct_score, grid, markets
from .models_data import Fixture, MatchResult
from .models_pred import Prediction

MODEL = "m1-dixon-coles-1"
class TooLate(Exception): ...

def latest_live(db: Session, fixture_id: int):
    sup = select(Prediction.supersedes_id).where(Prediction.supersedes_id.is_not(None))
    return db.scalar(select(Prediction).where(Prediction.fixture_id == fixture_id, Prediction.kind == "live", Prediction.id.not_in(sup)).order_by(Prediction.id.desc()))

def generate(db: Session, fx: Fixture, now=None, force=False):
    """Returns (Prediction, reused) or InsufficientData. Raises TooLate once kickoff has passed."""
    now = now or utcnow().replace(tzinfo=None)
    if fx.kickoff_utc <= now or fx.status != "scheduled": raise TooLate("fixture is not an upcoming scheduled match")
    prev = latest_live(db, fx.id)
    if prev and not force: return prev, True
    rows = list(db.execute(select(Fixture, MatchResult).join(MatchResult, MatchResult.fixture_id == Fixture.id)
                           .where(Fixture.competition_id == fx.competition_id, Fixture.kickoff_utc < now)))
    ms = [Match(f.kickoff_utc, str(f.home_team_id), str(f.away_team_id), r.home_goals, r.away_goals) for f, r in rows]
    f = fit(ms, now)
    if isinstance(f, InsufficientData): return f
    r = rates(f, str(fx.home_team_id), str(fx.away_team_id))
    if isinstance(r, InsufficientData): return r
    g = grid(*r, f.rho)
    p = Prediction(fixture_id=fx.id, kind="live", model_version=MODEL, data_cutoff_at=now, kickoff_utc=fx.kickoff_utc,
        probabilities={**markets(g), "correct_score": correct_score(g)},
        features={"home_xg": r[0], "away_xg": r[1], "rho": f.rho, "home_adv": f.home_adv, "training_matches": len(ms),
                  "home_matches": f.teams_matches[str(fx.home_team_id)], "away_matches": f.teams_matches[str(fx.away_team_id)], "decay_xi": 0.003},
        supersedes_id=prev.id if prev else None)
    db.add(p); db.commit(); return p, False
