import csv, io
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Sel:
    id: str
    fixture: str
    market: str
    outcome: str
    odds: Decimal
    model_p: float | None = None

def combined_odds(sels: list[Sel]) -> Decimal:
    r = Decimal(1)
    for s in sels:
        r *= s.odds  # never rounded
    return r

def display_odds(d: Decimal) -> str:
    return f"{d.quantize(Decimal('0.01')):.2f}"

def validate(sels: list[Sel]) -> list[str]:
    out, seen, by_fx = [], set(), {}
    for s in sels:
        if s.odds <= 1: out.append(f"{s.id}: odds must be greater than 1.00")
        k = (s.fixture, s.market, s.outcome)
        if k in seen: out.append(f"{s.id}: duplicate selection")
        seen.add(k); by_fx.setdefault(s.fixture, []).append(s)
    for fx, ss in by_fx.items():
        if len(ss) > 1:
            out.append(f"{fx}: correlated selections from the same match; combined odds assume independence")
        mk = {}
        for s in ss:
            if s.market in ("1x2", "btts") and mk.setdefault(s.market, s.outcome) != s.outcome:
                out.append(f"{fx}: contradictory {s.market} selections")
    return out

def split(sels: list[Sel], parts: int, strategy: str = "count") -> list[list[Sel]]:
    if parts < 1: raise ValueError("parts must be >= 1")
    if strategy == "count":
        order = list(sels)
    elif strategy == "probability":
        order = sorted(sels, key=lambda s: (-(s.model_p if s.model_p is not None else -1), s.id))
    elif strategy == "odds":
        order = sorted(sels, key=lambda s: (-s.odds, s.id))
    else:
        raise ValueError("unknown strategy")
    out = [[] for _ in range(parts)]
    for k, s in enumerate(order):
        out[k % parts].append(s)
    return out

def csv_safe(v: str) -> str:
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

def export_csv(sels: list[Sel]) -> str:
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["fixture", "market", "outcome", "odds"])
    for s in sels:
        w.writerow([csv_safe(s.fixture), csv_safe(s.market), csv_safe(s.outcome), str(s.odds)])
    return buf.getvalue()

def optimise(sels, max_odds: Decimal, max_sel: int, min_p: float):
    """Returns (kept, [(selection, reason)]). Never claims safety."""
    kept, removed = [], []
    for s in sorted(sels, key=lambda s: (-(s.model_p or 0), s.id)):
        if s.model_p is None:
            removed.append((s, "no model probability; constraint: minimum model probability")); continue
        if s.model_p < min_p:
            removed.append((s, f"model probability {s.model_p:.2f} below minimum {min_p:.2f}")); continue
        if len(kept) >= max_sel:
            removed.append((s, f"exceeds maximum selections ({max_sel})")); continue
        if combined_odds(kept + [s]) > max_odds:
            removed.append((s, f"would push combined odds above {max_odds}")); continue
        kept.append(s)
    return kept, removed
