"""python -m app.jobs run <job_name>. Each job takes a lock, records a data_sync_runs row, and is idempotent."""
import hashlib, sys, threading
from datetime import timedelta
import numpy as np
from sqlalchemy import delete, select, text
from .config import settings
from .db import SessionLocal, init_db
from .engine.metrics import brier_each, logloss_each, rps_each
from .models_chat import Conversation, Message
from .models_data import DataSyncRun, Fixture, MarketOdds, MatchResult, ProviderRawPayload
from .models_extra import AppSetting, PredictionEvaluation
from .models_pred import Prediction
from .models_tickets import IdempotencyKey, PendingChange, now_naive
from . import predictions

class Unavailable(Exception): ...
_locks: dict = {}
def retention_days(db):
    r = db.get(AppSetting, "retention_days"); return int(r.value) if r else 365

def prediction_evaluation(db):
    n = 0
    for p, f, r in db.execute(select(Prediction, Fixture, MatchResult).join(Fixture, Fixture.id == Prediction.fixture_id).join(MatchResult, MatchResult.fixture_id == Fixture.id)
                              .where(Prediction.kind == "live", Prediction.id.not_in(select(PredictionEvaluation.prediction_id)))):
        y = 0 if r.home_goals > r.away_goals else (1 if r.home_goals == r.away_goals else 2); q = p.probabilities["1x2"]
        P = np.array([[q["home"], q["draw"], q["away"]]]); Y = np.array([y])
        db.add(PredictionEvaluation(prediction_id=p.id, outcome=y, log_loss=float(logloss_each(P, Y)[0]), brier=float(brier_each(P, Y)[0]), rps=float(rps_each(P, Y)[0]))); n += 1
    db.commit(); return {"inserted": n}

def prediction_generation(db):
    now = now_naive(); ins = skip = 0
    for f in db.scalars(select(Fixture).where(Fixture.status == "scheduled", Fixture.kickoff_utc > now, Fixture.kickoff_utc < now + timedelta(hours=48))):
        res = predictions.generate(db, f)
        if isinstance(res, tuple) and not res[1]: ins += 1
        else: skip += 1
    return {"inserted": ins, "skipped": skip}

def retention_purge(db):
    cut = now_naive() - timedelta(days=retention_days(db)); n = 0
    for stmt in (delete(Message).where(Message.created_at < cut), delete(ProviderRawPayload).where(ProviderRawPayload.fetched_at < cut),
                 delete(MarketOdds).where(MarketOdds.observed_at < cut), delete(IdempotencyKey).where(IdempotencyKey.created_at < now_naive() - timedelta(days=2)),
                 delete(PendingChange).where(PendingChange.expires_at < now_naive())):
        n += db.execute(stmt).rowcount or 0
    n += db.execute(delete(Conversation).where(Conversation.created_at < cut, Conversation.id.not_in(select(Message.conversation_id)))).rowcount or 0
    db.commit(); return {"deleted": n}

def _need_provider(db): raise Unavailable("requires provider credentials and a live data source; not runnable or verified in this build")
JOBS = {"prediction_evaluation": prediction_evaluation, "prediction_generation": prediction_generation, "retention_purge": retention_purge,
        "fixture_sync": _need_provider, "odds_refresh": _need_provider, "result_import": _need_provider, "model_training": _need_provider}

def run_job(name: str) -> dict:
    if name not in JOBS: raise KeyError(name)
    init_db(); key = int(hashlib.sha256(name.encode()).hexdigest()[:15], 16); pg = settings.database_url.startswith("postgres")
    with SessionLocal() as db:
        run = DataSyncRun(job=name, started_at=now_naive(), status="running"); db.add(run); db.commit()
        got = (db.execute(text("select pg_try_advisory_lock(:k)"), {"k": key}).scalar() if pg else _locks.setdefault(name, threading.Lock()).acquire(blocking=False))
        if not got: run.status, run.ended_at = "skipped_locked", now_naive(); db.commit(); return {"status": "skipped_locked"}
        try:
            r = JOBS[name](db); run.status = "ok"; run.inserted = r.get("inserted", 0); run.skipped = r.get("skipped", 0); run.updated = r.get("deleted", 0)
        except Unavailable as e: run.status, run.error_summary = "unavailable", str(e)
        except Exception as e: db.rollback(); run.status, run.error_summary = "failed", type(e).__name__
        finally:
            if pg: db.execute(text("select pg_advisory_unlock(:k)"), {"k": key})
            else: _locks[name].release()
        run.ended_at = now_naive(); db.commit(); return {"status": run.status, "error": run.error_summary, "inserted": run.inserted, "skipped": run.skipped, "updated": run.updated}

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "run" or sys.argv[2] not in JOBS: sys.exit("usage: python -m app.jobs run <" + "|".join(JOBS) + ">")
    print(run_job(sys.argv[2]))
