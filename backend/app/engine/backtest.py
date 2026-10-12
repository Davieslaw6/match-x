"""Expanding-window walk-forward backtest. Each prediction uses a model fitted only on matches kicking off strictly before the cutoff."""
from datetime import timedelta
import numpy as np
from .dixon_coles import InsufficientData, Match, fit, rates
from .m0 import fit_m0, rates_m0
from .markets import grid, markets

def p1x2(lh, la, rho=0.0):
    m = markets(grid(lh, la, rho))["1x2"]; return [m["home"], m["draw"], m["away"]]

def outcome(m: Match): return 0 if m.hg > m.ag else (1 if m.hg == m.ag else 2)

def walk_forward(matches: list[Match], start_frac=0.4, step_days=21, xi=0.003):
    ms = sorted(matches, key=lambda m: m.kickoff)
    t = ms[int(len(ms) * start_frac)].kickoff; end = ms[-1].kickoff + timedelta(days=1)
    rows, skipped = [], 0
    while t < end:
        nxt = t + timedelta(days=step_days)
        f1, f0 = fit(ms, t, xi=xi), fit_m0(ms, t)
        for m in (x for x in ms if t <= x.kickoff < nxt):
            league = np.array([sum(outcome(x) == k for x in ms if x.kickoff < t) for k in range(3)], float)
            r1 = rates(f1, m.home, m.away) if not isinstance(f1, InsufficientData) else f1
            r0 = rates_m0(f0, m.home, m.away) if not isinstance(f0, InsufficientData) else f0
            if isinstance(r1, InsufficientData) or isinstance(r0, InsufficientData) or league.sum() == 0: skipped += 1; continue
            try:
                row = {"y": outcome(m), "uniform": [1/3]*3, "base_rate": list(league / league.sum()),
                       "m0": p1x2(*r0), "m1": p1x2(*r1, f1.rho), "cutoff": t}
            except ValueError:  # degenerate rates or grid mass below threshold: refuse, never emit a number
                skipped += 1; continue
            rows.append(row)
        t = nxt
    return rows, skipped
