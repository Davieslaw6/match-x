import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import auth
from app.db import SessionLocal

PW = "correct horse battery"
@pytest.fixture(scope="module", autouse=True)
def owner():
    with SessionLocal() as db: auth.create_owner(db, "owner", PW)

def fresh():
    c = TestClient(app, raise_server_exceptions=False)
    c.csrf = c.get("/api/v1/auth/session").json()["csrf_token"]; return c
def signin(c, pw=PW):
    return c.post("/api/v1/auth/login", json={"username": "owner", "password": pw}, headers={"x-csrf-token": c.csrf})
def h(c): return {"x-csrf-token": c.cookies["mx_csrf"]}

def test_anonymous_rejected():
    c = fresh()
    for p in ("/api/v1/odds/devig", "/api/v1/tickets/analyze", "/api/v1/predict/from-rates"):
        assert c.post(p, json={}, headers={"x-csrf-token": c.csrf}).status_code == 401

def test_login_requires_csrf_and_sets_httponly_cookie():
    c = TestClient(app); assert c.post("/api/v1/auth/login", json={"username": "owner", "password": PW}).status_code == 403
    c = fresh(); r = signin(c); assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()

def test_state_change_needs_csrf_header():
    c = fresh(); signin(c)
    assert c.post("/api/v1/odds/devig", json={"odds": ["2.0", "2.0"]}).status_code == 403
    r = c.post("/api/v1/odds/devig", json={"odds": ["2.0", "2.0"]}, headers=h(c)); assert r.status_code == 200
    assert r.json()["fair"][0].startswith("0.5")

def test_predict_and_ticket_endpoints():
    c = fresh(); signin(c)
    r = c.post("/api/v1/predict/from-rates", json={"home_xg": 1.6, "away_xg": 1.1, "rho": -0.05}, headers=h(c)).json()
    assert abs(sum(r["markets"]["1x2"].values()) - 1) < 1e-9
    t = {"selections": [{"id": "a", "fixture": "f1", "market": "1x2", "outcome": "h", "odds": "1.5"},
                        {"id": "b", "fixture": "f1", "market": "btts", "outcome": "yes", "odds": "1.8"}]}
    r = c.post("/api/v1/tickets/analyze", json=t, headers=h(c)).json()
    assert r["combined_odds"] == "2.70" and any("correlated" in w for w in r["warnings"])
    t["selections"][0]["fixture"] = "=HYPERLINK(1)"
    assert "'=HYPERLINK" in c.post("/api/v1/tickets/export.csv", json=t, headers=h(c)).text

def test_bad_input_is_enveloped_not_leaked():
    c = fresh(); signin(c)
    r = c.post("/api/v1/odds/devig", json={"odds": ["1.0", "2.0"]}, headers=h(c)); assert r.status_code == 422

def test_logout_invalidates_session():
    c = fresh(); signin(c); assert c.post("/api/v1/auth/logout", headers=h(c)).status_code == 200
    assert c.post("/api/v1/odds/devig", json={"odds": ["2", "2"]}, headers=h(c)).status_code == 401

def test_lockout_after_failures():
    c = fresh()
    for _ in range(5): assert signin(c, "wrong-password-x").status_code == 401
    assert signin(c).status_code == 429
