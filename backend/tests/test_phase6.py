from datetime import datetime, timedelta
from decimal import Decimal as D
import numpy as np, pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from app import auth, predictions
from app.db import LoginFailure, SessionLocal, init_db, utcnow
from app.main import app
from app.models_data import *
from app.models_pred import Prediction
from app.odds import analysis as oa
init_db()
NOW = lambda: utcnow().replace(tzinfo=None)
T = ["Alder", "Birch", "Cedar", "Dunmore", "Elmwood", "Fenwick", "Garth"]
IDS = {}

@pytest.fixture(scope="module", autouse=True)
def seed():
    """Synthetic TEST data only."""
    with SessionLocal() as db:
        c = Competition(code="P6", name="Phase Six League"); db.add(c); ts = {}
        for n in T:
            t = Team(name=n, norm=n.lower()); db.add(t); ts[n] = t
        db.flush(); rng = np.random.default_rng(5); k = 0
        for a in T:
            for b in T:
                if a == b: continue
                f = Fixture(provider="p6", provider_fixture_id=f"h{k}", competition_id=c.id, season="2026", home_team_id=ts[a].id, away_team_id=ts[b].id,
                            kickoff_utc=NOW() - timedelta(days=260 - k * 5), status="finished"); db.add(f); db.flush()
                db.add(MatchResult(fixture_id=f.id, home_goals=int(rng.poisson(1.5)), away_goals=int(rng.poisson(1.1)))); k += 1
        def fx(key, h, a, delta, st="scheduled"):
            f = Fixture(provider="p6", provider_fixture_id=key, competition_id=c.id, season="2026", home_team_id=ts[h].id, away_team_id=ts[a].id,
                        kickoff_utc=NOW() + delta, status=st); db.add(f); db.flush(); IDS[key] = f.id; return f
        up = fx("up", "Alder", "Birch", timedelta(days=3)); fx("nodata", "Cedar", "Dunmore", timedelta(days=4))
        fx("past", "Elmwood", "Fenwick", timedelta(days=-1)); st = fx("staleodds", "Garth", "Alder", timedelta(days=5))
        for bk, ago, vals in (("TestBook", timedelta(minutes=10), (2.1, 3.4, 3.6)), ("OldBook", timedelta(days=3), (2.0, 3.3, 3.5))):
            for s, v in zip(("home", "draw", "away"), vals):
                db.add(MarketOdds(fixture_id=up.id, bookmaker=bk, market="1x2", selection=s, decimal_odds=D(str(v)), observed_at=NOW() - ago, provider="p6"))
        for s, v in zip(("home", "draw", "away"), (2.0, 3.3, 3.5)):
            db.add(MarketOdds(fixture_id=st.id, bookmaker="Old", market="1x2", selection=s, decimal_odds=D(str(v)), observed_at=NOW() - timedelta(days=2), provider="p6"))
        db.commit()

PW = "correct horse battery"
def client():
    with SessionLocal() as db:
        try: auth.create_owner(db, "owner", PW)
        except ValueError: pass
        db.query(LoginFailure).delete(); db.commit()
    c = TestClient(app); c.csrf = c.get("/api/v1/auth/session").json()["csrf_token"]
    assert c.post("/api/v1/auth/login", json={"username": "owner", "password": PW}, headers={"x-csrf-token": c.csrf}).status_code == 200
    c.h = {"x-csrf-token": c.cookies["mx_csrf"]}; return c

def test_staleness_tightens_toward_kickoff():
    ko = datetime(2027, 1, 10, 15); at = lambda mins: ko - timedelta(minutes=mins)
    assert [oa.stale_minutes(m) for m in (3000, 600, 90, 0, -5)] == [360, 120, 30, 0, 0]
    assert not oa.is_stale(at(135), ko, at(120)) and oa.is_stale(at(160), ko, at(120))  # 15 min old is fresh, 40 min old is stale at 2h out
    assert oa.is_stale(at(1), ko, ko + timedelta(minutes=1))

def test_compare_math_and_ev_gating():
    o = {"home": D("2.0"), "draw": D("4.0"), "away": D("4.0")}; mp = {"home": 0.60, "draw": 0.2, "away": 0.2}
    c = oa.compare(o, mp, fresh=True); assert c["overround"] == "0.0000"
    assert c["selections"]["home"]["fair_prob"] == "0.5000" and c["selections"]["home"]["theoretical_ev"] == "0.2000" and "caution" in c["selections"]["home"]
    assert "theoretical_ev" not in oa.compare(o, mp, fresh=False)["selections"]["home"]
    assert "model_prob" not in oa.compare(o, None, fresh=True)["selections"]["home"]

def test_prediction_db_rules():
    with SessionLocal() as db:
        k = datetime(2030, 1, 1)
        bad = Prediction(fixture_id=IDS["up"], kind="live", model_version="x", data_cutoff_at=k, kickoff_utc=k, probabilities={}, features={})
        db.add(bad)
        with pytest.raises(IntegrityError): db.flush()
        db.rollback()
        db.add(Prediction(fixture_id=IDS["up"], kind="backtest", model_version="x", data_cutoff_at=k, kickoff_utc=k, probabilities={}, features={})); db.flush(); db.rollback()

def test_generate_reuse_supersede_immutability_and_too_late():
    with SessionLocal() as db:
        fx = db.get(Fixture, IDS["up"]); p1, reused = predictions.generate(db, fx); assert not reused and p1.supersedes_id is None
        assert abs(sum(p1.probabilities["1x2"].values()) - 1) < 1e-9 and p1.data_cutoff_at < fx.kickoff_utc and p1.created_at < fx.kickoff_utc
        p1b, reused = predictions.generate(db, fx); assert reused and p1b.id == p1.id
        p2, reused = predictions.generate(db, fx, force=True); assert not reused and p2.supersedes_id == p1.id
        assert predictions.latest_live(db, fx.id).id == p2.id
        p1.model_version = "tampered"
        with pytest.raises(ValueError, match="immutable"): db.flush()
        db.rollback()
        with pytest.raises(predictions.TooLate): predictions.generate(db, db.get(Fixture, IDS["past"]))

def test_explorer_requires_login_validates_and_paginates():
    anon = TestClient(app); assert anon.get("/api/v1/fixtures").status_code == 401
    c = client()
    assert c.get("/api/v1/fixtures?page_size=500").status_code == 422 and c.get("/api/v1/fixtures?status=bogus").status_code == 422
    r = c.get("/api/v1/fixtures?competition=P6&page_size=10&page=2").json(); assert r["total"] == 46 and len(r["items"]) == 10 and r["page"] == 2
    up = c.get("/api/v1/fixtures?competition=P6&status=scheduled").json(); assert up["total"] == 4
    assert {i["home"] for i in c.get("/api/v1/fixtures?competition=P6&q=alder&status=scheduled").json()["items"]} >= {"Alder"}
    first = c.get(f"/api/v1/fixtures?competition=P6&status=scheduled&date_from={(NOW()+timedelta(days=2)).date()}&date_to={(NOW()+timedelta(days=3)).date()}").json()
    assert first["total"] >= 1 and first["items"][0]["prediction_available"] in (True, False)

def test_favourites_filter():
    c = client()
    with SessionLocal() as db: gid = db.query(Team).filter_by(name="Garth").one().id
    assert c.put(f"/api/v1/teams/{gid}/favourite", json={"value": True}, headers=c.h).json()["favourite"] is True
    items = c.get("/api/v1/fixtures?competition=P6&favourites_only=true").json()["items"]; assert items and all("Garth" in (i["home"], i["away"]) for i in items)
    assert c.put("/api/v1/teams/99999/favourite", json={"value": True}, headers=c.h).status_code == 404

def test_kickoff_local_uses_configured_timezone_across_dst(monkeypatch):
    from app import explorer; from app.config import settings
    monkeypatch.setattr(settings, "timezone", "Europe/London")
    assert explorer.local(datetime(2026, 1, 15, 12)).endswith("+00:00") and explorer.local(datetime(2026, 7, 15, 12)).startswith("2026-07-15T13:00")
    assert explorer.local(datetime(2026, 3, 29, 0, 30)).endswith("+00:00") and explorer.local(datetime(2026, 3, 29, 1, 30)).startswith("2026-03-29T02:30")

def test_analysis_missing_data_then_prediction_and_odds():
    c = client()
    nd = c.get(f"/api/v1/fixtures/{IDS['nodata']}/analysis").json()
    assert nd["prediction"] is None and nd["odds"] is None
    w = " ".join(nd["warnings"]); assert "No stored prediction" in w and "No complete 1X2 odds" in w and "Expected goals are unavailable" in w and "Injuries" in w
    assert nd["expected_goals"]["status"] == "unavailable"
    up = c.get(f"/api/v1/fixtures/{IDS['up']}/analysis?n=5").json()
    assert up["prediction"]["model_version"] and up["odds"]["bookmaker"] == "TestBook" and up["odds"]["stale"] is False
    sel = up["odds"]["comparison"]["selections"]["home"]; assert "theoretical_ev" in sel and "model_prob" in sel
    assert "Statistical estimates" in up["notice"] and "fitted on" in up["explanation"] and up["form"]["home"]["status"] == "ok"
    assert up["splits"]["home_team_at_home"]["played"] > 0 and up["head_to_head"]["played"] > 0

def test_stale_odds_flagged_and_no_ev_without_prediction():
    c = client(); r = c.get(f"/api/v1/fixtures/{IDS['staleodds']}/analysis").json()
    assert r["odds"]["stale"] is True and any("stale" in w.lower() for w in r["warnings"])
    assert "theoretical_ev" not in r["odds"]["comparison"]["selections"]["home"]

def test_prediction_endpoint_csrf_reuse_and_409():
    c = client(); u = f"/api/v1/fixtures/{IDS['staleodds']}/predictions"
    assert c.post(u, json={}).status_code == 403
    r1 = c.post(u, json={}, headers=c.h).json(); r2 = c.post(u, json={}, headers=c.h).json()
    assert r1["reused"] is False and r2["reused"] is True and r1["prediction"]["id"] == r2["prediction"]["id"]
    assert c.post(f"/api/v1/fixtures/{IDS['past']}/predictions", json={}, headers=c.h).status_code == 409
    assert c.post("/api/v1/fixtures/999999/predictions", json={}, headers=c.h).status_code == 404

def test_get_prediction_tool():
    from app.ai.tools import GetPredIn, get_prediction
    with SessionLocal() as db:
        assert get_prediction(db, GetPredIn(fixture_id=IDS["up"]))["status"] == "ok" and get_prediction(db, GetPredIn(fixture_id=IDS["nodata"]))["status"] == "none"
