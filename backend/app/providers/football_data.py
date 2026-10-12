from datetime import date
import httpx
from pydantic import BaseModel, ValidationError
from .base import Capabilities, NormFixture, SportsDataProvider
from .resilience import CircuitBreaker, QuotaBudget, get_json

STATUS = {"SCHEDULED": "scheduled", "TIMED": "scheduled", "IN_PLAY": "live", "PAUSED": "live", "FINISHED": "finished",
          "POSTPONED": "postponed", "SUSPENDED": "postponed", "CANCELLED": "cancelled", "AWARDED": "finished"}

class _T(BaseModel): name: str
class _FT(BaseModel): home: int | None = None; away: int | None = None
class _Score(BaseModel): fullTime: _FT = _FT()
class _Season(BaseModel): startDate: str
class _M(BaseModel):
    id: int; utcDate: "datetime"; status: str; homeTeam: _T; awayTeam: _T; score: _Score = _Score()
    season: _Season
from datetime import datetime  # noqa: E402
_M.model_rebuild()

class FootballDataOrg(SportsDataProvider):
    """football-data.org v4. UNVERIFIED live: coverage, rate limit and licence must be checked in docs/api-setup.md."""
    name = "football-data.org"; capabilities = Capabilities()
    def __init__(self, client: httpx.AsyncClient, token: str, budget: QuotaBudget, breaker: CircuitBreaker, sleep=None):
        self.c, self.token, self.budget, self.breaker = client, token, budget, breaker
        self.sleep = sleep
    async def fixtures(self, competition_code: str, start: date, end: date):
        kw = {"sleep": self.sleep} if self.sleep else {}
        data = await get_json(self.c, f"https://api.football-data.org/v4/competitions/{competition_code}/matches",
            budget=self.budget, breaker=self.breaker, headers={"X-Auth-Token": self.token},
            params={"dateFrom": start.isoformat(), "dateTo": end.isoformat()}, **kw)
        good, rejected = [], []
        for raw in data.get("matches", []):
            try:
                m = _M.model_validate(raw)
                if m.status not in STATUS: raise ValueError(f"unknown status {m.status}")
                good.append(NormFixture(provider=self.name, provider_fixture_id=str(m.id), competition_code=competition_code,
                    season=m.season.startDate[:4], home=m.homeTeam.name, away=m.awayTeam.name,
                    kickoff_utc=m.utcDate.replace(tzinfo=None) if m.utcDate.tzinfo is None else m.utcDate.astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None),
                    status=STATUS[m.status], home_goals=m.score.fullTime.home, away_goals=m.score.fullTime.away))
            except (ValidationError, ValueError) as e:
                rejected.append((raw.get("id"), str(e)[:120]))
        return good, rejected, data
