import hashlib, json
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import utcnow
from .models_data import *  # noqa
from .providers.teams import normalise, resolve

TOL = timedelta(hours=3)

def team_id(db: Session, name: str):
    """Returns team id, or None if ambiguous (caller counts it as failed)."""
    aliases = {a.alias_norm: db.get(Team, a.team_id).name for a in db.scalars(select(TeamAlias))}
    teams = list(db.scalars(select(Team)))
    kind, val = resolve(name, aliases, [t.name for t in teams])
    if kind == "match": return next(t.id for t in teams if t.name == val)
    if kind == "ambiguous": return None
    t = Team(name=name, norm=normalise(name)); db.add(t); db.flush(); return t.id

def upsert(db: Session, nf, comp_id: int) -> str:
    h, a = team_id(db, nf.home), team_id(db, nf.away)
    if h is None or a is None: return "failed"
    fx = db.scalar(select(Fixture).where(Fixture.provider == nf.provider, Fixture.provider_fixture_id == nf.provider_fixture_id))
    if fx is None:  # canonical duplicate check across providers
        fx = db.scalar(select(Fixture).where(Fixture.competition_id == comp_id, Fixture.season == nf.season,
            Fixture.home_team_id == h, Fixture.away_team_id == a,
            Fixture.kickoff_utc.between(nf.kickoff_utc - TOL, nf.kickoff_utc + TOL)))
        if fx is not None:
            res = db.scalar(select(MatchResult).where(MatchResult.fixture_id == fx.id))
            return _set_result(db, fx, nf, res, existing=True)
    if fx is None:
        fx = Fixture(provider=nf.provider, provider_fixture_id=nf.provider_fixture_id, competition_id=comp_id, season=nf.season,
                     home_team_id=h, away_team_id=a, kickoff_utc=nf.kickoff_utc, status=nf.status)
        db.add(fx); db.flush(); _set_result(db, fx, nf, None, existing=False); return "inserted"
    res = db.scalar(select(MatchResult).where(MatchResult.fixture_id == fx.id))
    changed = (fx.status, fx.kickoff_utc) != (nf.status, nf.kickoff_utc)
    fx.status, fx.kickoff_utc = nf.status, nf.kickoff_utc
    r = _set_result(db, fx, nf, res, existing=True)
    return "updated" if changed or r == "updated" else "skipped"

def _set_result(db, fx, nf, res, existing):
    if nf.home_goals is None or nf.away_goals is None or nf.status != "finished": return "skipped" if existing else None
    if res is None:
        db.add(MatchResult(fixture_id=fx.id, home_goals=nf.home_goals, away_goals=nf.away_goals)); return "updated" if existing else None
    if (res.home_goals, res.away_goals) != (nf.home_goals, nf.away_goals):
        res.home_goals, res.away_goals = nf.home_goals, nf.away_goals; return "updated"
    return "skipped"

def run_sync(db: Session, job: str, comp_code: str, fixtures, rejected=(), raw=None):
    run = DataSyncRun(job=job, started_at=utcnow().replace(tzinfo=None), status="running"); db.add(run); db.flush()
    comp = db.scalar(select(Competition).where(Competition.code == comp_code))
    if comp is None: comp = Competition(code=comp_code, name=comp_code); db.add(comp); db.flush()
    if raw is not None:
        blob = json.dumps(raw, sort_keys=True)
        db.add(ProviderRawPayload(provider=fixtures[0].provider if fixtures else job, payload=raw,
               content_hash=hashlib.sha256(blob.encode()).hexdigest(), fetched_at=run.started_at))
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": len(rejected)}
    for nf in fixtures: counts[upsert(db, nf, comp.id)] += 1
    for k, v in counts.items(): setattr(run, k, v)
    run.status = "partial" if counts["failed"] else "ok"; run.ended_at = utcnow().replace(tzinfo=None)
    if rejected: run.error_summary = "; ".join(f"{i}: {r}" for i, r in rejected[:5])[:500]
    db.commit(); return run
