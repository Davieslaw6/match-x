"""football-data.co.uk CSV importer. Kickoff dates are UK local time; converted to UTC (DST-aware)."""
import csv, io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from .base import NormFixture

LON = ZoneInfo("Europe/London"); UTC = ZoneInfo("UTC")

def parse(text: str, competition_code: str, season: str):
    fixtures, odds, rejected = [], [], []
    for n, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        try:
            d = datetime.strptime(row["Date"], "%d/%m/%Y" if len(row["Date"]) == 10 else "%d/%m/%y")
            t = datetime.strptime(row.get("Time") or "12:00", "%H:%M").time()
            ko = d.replace(hour=t.hour, minute=t.minute, tzinfo=LON).astimezone(UTC).replace(tzinfo=None)
            hg, ag = int(row["FTHG"]), int(row["FTAG"])
            if hg < 0 or ag < 0: raise ValueError("negative goals")
            h, a = row["HomeTeam"].strip(), row["AwayTeam"].strip()
            if not h or not a or h == a: raise ValueError("bad teams")
            fid = f"{competition_code}-{season}-{ko:%Y%m%d}-{h}-{a}"
            nf = (NormFixture(provider="football-data.co.uk", provider_fixture_id=fid, competition_code=competition_code,
                season=season, home=h, away=a, kickoff_utc=ko, status="finished", home_goals=hg, away_goals=ag))
            row_odds = []
            for col, sel in (("PSCH", "home"), ("PSCD", "draw"), ("PSCA", "away")):
                if row.get(col):
                    o = Decimal(row[col])
                    if o <= 1: raise ValueError(f"{col} must exceed 1.00")
                    row_odds.append((fid, "Pinnacle", "1x2", sel, o))
            fixtures.append(nf); odds.extend(row_odds)  # accept the row only if everything parsed
        except (KeyError, ValueError, InvalidOperation) as e:
            rejected.append((n, str(e)[:100]))
    return fixtures, odds, rejected
