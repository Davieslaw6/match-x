import math
from datetime import datetime, timedelta
from decimal import Decimal as D
import numpy as np, pytest
from hypothesis import given, assume, strategies as st
from app.engine.markets import grid, markets
from app.engine.dixon_coles import Match, InsufficientData, fit, rates
from app.odds.core import *
from app.tickets.core import *
from app.providers.teams import normalise, resolve
from app.bookings import Job, advance, create, ManualIntegration

rate = st.floats(0.2, 4.0); rho = st.floats(-0.1, 0.1)

@given(rate, rate, rho)
def test_market_invariants(lh, la, r):
    try: g = grid(lh, la, r)
    except ValueError: return
    m = markets(g)
    assert (g >= 0).all() and math.isclose(g.sum(), 1, abs_tol=1e-9)
    assert math.isclose(sum(m["1x2"].values()), 1, abs_tol=1e-9)
    for v in m["over_under"].values(): assert math.isclose(v["over"] + v["under"], 1, abs_tol=1e-9) or v["over"]+v["under"]<=1
    assert math.isclose(m["btts"]["yes"] + m["btts"]["no"], 1, abs_tol=1e-9)
    assert math.isclose(m["double_chance"]["1x"], m["1x2"]["home"] + m["1x2"]["draw"], abs_tol=1e-9)

def test_grid_rejects_low_mass():
    with pytest.raises(ValueError): grid(30, 30)

def _data():
    import random; rnd = random.Random(7); t0 = datetime(2024, 1, 1); ts = list("ABCDEF"); out = []
    for k in range(120):
        h, a = rnd.sample(ts, 2)
        out.append(Match(t0 + timedelta(days=k), h, a, rnd.randint(0, 3), rnd.randint(0, 2)))
    return out

def test_leakage_and_determinism():
    d = _data(); cut = datetime(2024, 3, 1); f1 = fit(d, cut)
    mutated = [m if m.kickoff < cut else Match(m.kickoff, m.home, m.away, 9, 9) for m in d] + d[-5:]
    f2 = fit(mutated, cut)
    assert f1 == f2  # identical despite changed/added post-cutoff rows
    assert fit(d, cut) == f1

def test_insufficient_data():
    assert isinstance(fit(_data(), datetime(2024, 1, 5)), InsufficientData)
    f = fit(_data(), datetime(2024, 5, 1)); assert isinstance(rates(f, "A", "Z"), InsufficientData)

def test_fit_gives_valid_probabilities():
    f = fit(_data(), datetime(2024, 5, 1)); lh, la = rates(f, "A", "B")
    assert math.isclose(sum(markets(grid(lh, la, f.rho))["1x2"].values()), 1, abs_tol=1e-9)

OD = st.lists(st.decimals(D("1.05"), D("20"), places=2), min_size=2, max_size=4)
@given(OD)
def test_devig_sums_to_one(o):
    assume(overround(o) >= 0)
    for fn in (devig_proportional, devig_power, devig_shin):
        assert abs(sum(fn(o)) - 1) < D("1e-5")

def test_odds_validation():
    with pytest.raises(ValueError): implied(D("1.00"))
    assert overround([D("2.0"), D("2.0")]) == 0

sel = st.builds(Sel, id=st.uuids().map(str), fixture=st.sampled_from(["f1", "f2", "f3"]),
    market=st.just("1x2"), outcome=st.sampled_from(["h", "d", "a"]),
    odds=st.decimals(D("1.01"), D("15"), places=3), model_p=st.floats(0.05, 0.95))

@given(st.lists(sel, min_size=1, max_size=12), st.integers(1, 5), st.sampled_from(["count", "odds", "probability"]))
def test_split_conserves_multiset(sels, n, strat):
    parts = split(sels, n, strat)
    assert sorted(s.id for p in parts for s in p) == sorted(s.id for s in sels)

@given(st.lists(sel, max_size=8))
def test_combined_is_exact_product(sels):
    exp = D(1)
    for s in sels: exp *= s.odds
    assert combined_odds(sels) == exp

def test_csv_injection_and_validation():
    s = Sel("1", "=cmd|' /C calc'!A0", "+x", "-y", D("2"))
    out = export_csv([s]); assert "'=cmd" in out and "'+x" in out and "'-y" in out
    a = Sel("a", "f", "1x2", "h", D("2")); b = Sel("b", "f", "1x2", "a", D("2"))
    msgs = validate([a, b, a]); assert any("contradictory" in m for m in msgs)
    assert any("correlated" in m for m in msgs) and any("duplicate" in m for m in msgs)

def test_optimiser_explains_removals():
    s = [Sel("a", "f1", "1x2", "h", D("2"), .6), Sel("b", "f2", "1x2", "h", D("3"), .2)]
    kept, rem = optimise(s, D("10"), 5, .5)
    assert [k.id for k in kept] == ["a"] and "below minimum" in rem[0][1]

def test_team_resolution():
    assert normalise("Atlético Madrid FC") == "atletico madrid"
    teams = ["Manchester United", "Manchester City", "Arsenal"]
    assert resolve("Arsenal FC", {}, teams)[0] == "match"
    assert resolve("man", {}, teams)[0] in ("ambiguous", "none")
    assert resolve("man utd", {"man utd": "Manchester United"}, teams) == ("match", "Manchester United")

def test_booking_never_fabricates():
    j = Job()
    for s in ["resolved", "mapped", "previewed", "confirmed"]: advance(j, s)
    create(j, ManualIntegration(), []); assert j.status == "failed" and j.code is None
    with pytest.raises(ValueError): advance(Job(), "created")
    class Fake:
        supports_create = True
        def create_code(self, s): return {"code": "ABC", "confirmation_id": "c1"}
    j2 = Job("confirmed"); create(j2, Fake(), []); assert j2.status == "created" and j2.code == "ABC"
    class NoConf(Fake):
        def create_code(self, s): return {"code": "ABC"}
    j3 = Job("confirmed"); create(j3, NoConf(), []); assert j3.status == "failed" and j3.code is None
