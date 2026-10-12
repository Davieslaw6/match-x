from fastapi.testclient import TestClient
from app.main import app
c = TestClient(app, raise_server_exceptions=False)

def test_live():
    r = c.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}

def test_request_id_roundtrip():
    r = c.get("/api/v1/health/live", headers={"x-request-id": "abc"})
    assert r.headers["x-request-id"] == "abc"

def test_ready_reports_database_state():
    assert c.get("/api/v1/health/ready").status_code in (200, 503)
