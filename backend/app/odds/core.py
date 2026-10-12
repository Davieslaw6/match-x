from decimal import Decimal, getcontext
getcontext().prec = 28

def implied(odds: Decimal) -> Decimal:
    if odds <= 1:
        raise ValueError("decimal odds must exceed 1.00")
    return Decimal(1) / odds

def overround(odds: list[Decimal]) -> Decimal:
    return sum((implied(o) for o in odds), Decimal(0)) - 1

def devig_proportional(odds: list[Decimal]) -> list[Decimal]:
    q = [implied(o) for o in odds]; s = sum(q)
    return [x / s for x in q]

def devig_power(odds: list[Decimal]) -> list[Decimal]:
    if overround(odds) < 0: raise ValueError("negative overround: not a bookmaker market")
    q = [implied(o) for o in odds]
    lo, hi = Decimal("0.5"), Decimal(200)
    for _ in range(200):
        k = (lo + hi) / 2
        s = sum((x ** k for x in q), Decimal(0))
        lo, hi = (k, hi) if s > 1 else (lo, k)
    return [x ** ((lo + hi) / 2) for x in q]

def devig_shin(odds: list[Decimal]) -> list[Decimal]:
    if overround(odds) < 0: raise ValueError("negative overround: not a bookmaker market")
    q = [float(implied(o)) for o in odds]; S = sum(q)
    def total(z): return sum(((z * z + 4 * (1 - z) * x * x / S) ** .5 - z) / (2 * (1 - z)) for x in q)
    lo, hi = 0.0, 0.999
    for _ in range(200):
        z = (lo + hi) / 2
        lo, hi = (z, hi) if total(z) > 1 else (lo, z)
    z = (lo + hi) / 2
    p = [((z * z + 4 * (1 - z) * x * x / S) ** .5 - z) / (2 * (1 - z)) for x in q]
    s = sum(p)
    return [Decimal(str(x / s)) for x in p]

def theoretical_ev(model_p: Decimal, odds: Decimal) -> Decimal:
    """Theoretical only: model_p * odds - 1. Not profit."""
    return model_p * odds - 1
