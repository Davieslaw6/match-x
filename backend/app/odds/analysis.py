from datetime import datetime
from decimal import Decimal
from . import core

def stale_minutes(minutes_to_kickoff: float) -> int:
    """Staleness threshold tightens toward kickoff. After kickoff pre-match prices are always stale."""
    if minutes_to_kickoff <= 0: return 0
    return 30 if minutes_to_kickoff <= 180 else (120 if minutes_to_kickoff <= 1440 else 360)

def is_stale(observed: datetime, kickoff: datetime, now: datetime) -> bool:
    age = (now - observed).total_seconds() / 60
    return age > stale_minutes((kickoff - now).total_seconds() / 60)

def latest_complete_1x2(rows):
    """rows: MarketOdds-like with bookmaker/market/selection/decimal_odds/observed_at. Returns (bookmaker, {sel: odds}, observed_at) for the
    bookmaker whose most recent complete home/draw/away triple is newest, or None."""
    best = None
    by_bk = {}
    for r in rows:
        if r.market == "1x2": by_bk.setdefault(r.bookmaker, {}).setdefault(r.selection, []).append(r)
    for bk, sels in by_bk.items():
        if not {"home", "draw", "away"} <= sels.keys(): continue
        latest = {s: max(v, key=lambda r: r.observed_at) for s, v in sels.items() if s in ("home", "draw", "away")}
        when = min(r.observed_at for r in latest.values())  # triple is only as fresh as its oldest leg
        if best is None or when > best[2]: best = (bk, {s: Decimal(str(r.decimal_odds)) for s, r in latest.items()}, when)
    return best

LARGE = Decimal("0.10")
def compare(odds: dict, model_p: dict | None, fresh: bool) -> dict:
    sel = ("home", "draw", "away"); o = [odds[s] for s in sel]; fair = core.devig_proportional(o)
    out = {"overround": str(core.overround(o).quantize(Decimal("0.0001"))), "selections": {}}
    for s, price, f in zip(sel, o, fair):
        row = {"odds": str(price), "raw_implied": str(core.implied(price).quantize(Decimal("0.0001"))), "fair_prob": str(f.quantize(Decimal("0.0001")))}
        if model_p is not None:
            m = Decimal(str(round(model_p[s], 8))); row["model_prob"] = str(m.quantize(Decimal("0.0001"))); diff = m - f
            row["difference"] = str(diff.quantize(Decimal("0.0001")))
            if abs(diff) >= LARGE: row["caution"] = "Large gap between model and market; this often reflects model error or missing information such as team news."
            if fresh: row["theoretical_ev"] = str(core.theoretical_ev(m, price).quantize(Decimal("0.0001")))
        out["selections"][s] = row
    if model_p is not None and fresh: out["ev_note"] = "Theoretical expected value from the model's estimate, not a profit forecast."
    return out
