import numpy as np
from datetime import datetime, timedelta
from app.engine.backtest import walk_forward
from app.engine.dixon_coles import Match
from app.engine.metrics import *

def test_metric_known_values():
    U = np.full((4, 3), 1/3); y = np.array([0, 1, 2, 0])
    assert np.isclose(logloss_each(U, y).mean(), np.log(3))
    assert np.isclose(brier_each(U, y).mean(), 2/3)
    P = np.eye(3)[y]; assert rps_each(P, y).sum() == 0 and brier_each(P, y).sum() == 0
    assert rps_each(np.array([[0., 0., 1.]]), np.array([0]))[0] == 1.0  # worst ordered miss

def test_calibration_perfect_and_bootstrap_deterministic():
    P = np.array([[1., 0, 0]] * 5); y = np.zeros(5, int); assert calibration(P, y)[1] == 0
    v = np.arange(20.); assert bootstrap_ci(v, seed=1) == bootstrap_ci(v, seed=1)
    m, lo, hi = bootstrap_ci(v); assert lo < m < hi

def _data():
    rng = np.random.default_rng(3); out = []; t0 = datetime(2024, 1, 1)
    for k in range(160):
        h, a = rng.choice(6, 2, replace=False); out.append(Match(t0 + timedelta(days=k), f"T{h}", f"T{a}", int(rng.poisson(1.5)), int(rng.poisson(1.1))))
    return out

def test_walk_forward_uses_only_past_and_is_deterministic():
    d = _data(); r1, _ = walk_forward(d); r2, _ = walk_forward(d)
    assert r1 and [x["m1"] for x in r1] == [x["m1"] for x in r2]
    # Corrupting results after the first evaluated cutoff must not change earlier predictions.
    cut = r1[0]["cutoff"]; first = [x for x in r1 if x["cutoff"] == cut]
    d2 = [m if m.kickoff < cut else Match(m.kickoff, m.home, m.away, 9, 0) for m in d]
    r3, _ = walk_forward(d2); assert [x["m1"] for x in r3 if x["cutoff"] == cut] == [x["m1"] for x in first]
    assert all(abs(sum(x["m1"]) - 1) < 1e-9 for x in r1)
