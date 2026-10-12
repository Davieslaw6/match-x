import asyncio, httpx, pytest, respx
from datetime import date, datetime
from sqlalchemy import func, select
from app.db import SessionLocal, init_db
from app.models_data import Fixture, DataSyncRun, Team, MatchResult
from app.providers.base import SportsDataProvider, Unsupported
from app.providers.csv_import import parse
from app.providers.football_data import FootballDataOrg
from app.providers.resilience import *
from app.sync import run_sync
init_db()
NOSLEEP = lambda s: asyncio.sleep(0)
M = lambda i, h="Arsenal FC", a="Chelsea FC", st="FINISHED", ft=(2, 1): {"id": i, "utcDate": "2025-03-01T15:00:00Z", "status": st,
    "homeTeam": {"name": h}, "awayTeam": {"name": a}, "score": {"fullTime": {"home": ft[0], "away": ft[1]}}, "season": {"startDate": "2024-08-01"}}

def prov(budget=100):
    return FootballDataOrg(httpx.AsyncClient(), "tok", QuotaBudget(budget), CircuitBreaker(), sleep=NOSLEEP)

@respx.mock
def test_retry_after_then_success_and_rejects_invalid():
    route = respx.get(url__regex=r".*matches.*").mock(side_effect=[httpx.Response(429, headers={"retry-after": "1"}),
        httpx.Response(200, json={"matches": [M(1), {"id": 2, "bad": True}, M(3, st="WEIRD")]})])
    good, rejected, raw = asyncio.run(prov().fixtures("PL", date(2025, 3, 1), date(2025, 3, 2)))
    assert route.call_count == 2 and len(good) == 1 and len(rejected) == 2 and good[0].season == "2024"

@respx.mock
def test_client_error_not_retried_and_circuit_opens():
    route = respx.get(url__regex=r".*").mock(return_value=httpx.Response(500))
    p = prov()
    for _ in range(3):
        with pytest.raises(ProviderError): asyncio.run(p.fixtures("PL", date(2025, 1, 1), date(2025, 1, 2)))
    with pytest.raises(CircuitOpen): asyncio.run(p.fixtures("PL", date(2025, 1, 1), date(2025, 1, 2)))
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(403))
    with pytest.raises(ProviderError, match="403"): asyncio.run(prov().fixtures("PL", date(2025, 1, 1), date(2025, 1, 2)))

@respx.mock
def test_quota_exhaustion_refuses_calls():
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={"matches": []}))
    p = prov(budget=1); asyncio.run(p.fixtures("PL", date(2025, 1, 1), date(2025, 1, 2)))
    with pytest.raises(QuotaExhausted): asyncio.run(p.fixtures("PL", date(2025, 1, 1), date(2025, 1, 2)))

def test_unsupported_is_typed_not_empty():
    assert isinstance(asyncio.run(SportsDataProvider().fixtures("PL", date.today(), date.today())), Unsupported)
    assert isinstance(asyncio.run(prov().injuries()), Unsupported)

@respx.mock
def test_sync_idempotent_and_cross_provider_dedup():
    respx.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={"matches": [M(1), M(2, "Liverpool FC", "Everton FC", "SCHEDULED", (None, None))]}))
    good, rej, raw = asyncio.run(prov().fixtures("PL", date(2025, 3, 1), date(2025, 3, 2)))
    with SessionLocal() as db:
        r1 = run_sync(db, "fixture_sync", "PL", good, rej, raw); assert (r1.inserted, r1.skipped) == (2, 0)
        r2 = run_sync(db, "fixture_sync", "PL", good, rej, raw); assert (r2.inserted, r2.updated, r2.skipped) == (0, 0, 2)
        csv = "Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSCH,PSCD,PSCA\n01/03/2025,15:00,Arsenal,Chelsea,2,1,1.9,3.6,4.2\n"
        f, odds, rej2 = parse(csv, "PL", "2024")
        r3 = run_sync(db, "csv_import", "PL", f); assert r3.inserted == 0  # same match from a second provider
        assert db.scalar(select(func.count()).select_from(Fixture)) == 2
        assert db.scalar(select(func.count()).select_from(DataSyncRun)) == 3
        assert db.scalar(select(func.count()).select_from(MatchResult)) == 1

def test_csv_rejects_bad_rows_and_converts_dst():
    csv = ("Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSCH\n15/01/2025,20:00,A,B,1,0,2.0\n15/07/2025,20:00,A,B,1,0,2.0\n"
           "xx,20:00,A,B,1,0,2.0\n16/07/2025,20:00,A,A,1,0,2.0\n17/07/2025,20:00,A,B,-1,0,2.0\n18/07/2025,20:00,A,B,1,0,0.9\n")
    f, odds, rej = parse(csv, "PL", "2024")
    assert f[0].kickoff_utc.hour == 20 and f[1].kickoff_utc.hour == 19  # BST = UTC+1
    assert len(rej) == 4 and len(f) == 2
