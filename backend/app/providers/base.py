from dataclasses import dataclass
from datetime import date
from pydantic import BaseModel

@dataclass(frozen=True)
class Unsupported:
    capability: str
    provider: str

@dataclass(frozen=True)
class Capabilities:
    supports_odds: bool = False; supports_xg: bool = False; supports_injuries: bool = False
    supports_cards: bool = False; supports_corners: bool = False

class NormFixture(BaseModel):
    provider: str; provider_fixture_id: str; competition_code: str; season: str
    home: str; away: str; kickoff_utc: "datetime"; status: str
    home_goals: int | None = None; away_goals: int | None = None

from datetime import datetime  # noqa: E402
NormFixture.model_rebuild()

class SportsDataProvider:
    name = "base"; capabilities = Capabilities()
    async def fixtures(self, competition_code: str, start: date, end: date):
        return Unsupported("fixtures", self.name)
    async def odds(self, *a, **k): return Unsupported("odds", self.name) if not self.capabilities.supports_odds else None
    async def injuries(self, *a, **k): return Unsupported("injuries", self.name)
