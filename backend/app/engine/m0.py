"""M0 baseline: league-average independent Poisson with shrunk attack/defence strengths and home advantage."""
from dataclasses import dataclass
from datetime import datetime
from .dixon_coles import InsufficientData, Match

@dataclass(frozen=True)
class M0Fit:
    avg_home: float; avg_away: float; att: dict; dfn: dict; n: dict

def fit_m0(matches: list[Match], cutoff: datetime, shrink: float = 5.0, min_total: int = 20):
    ms = [m for m in matches if m.kickoff < cutoff]
    if len(ms) < min_total: return InsufficientData(f"only {len(ms)} matches before cutoff")
    avg_h = sum(m.hg for m in ms) / len(ms); avg_a = sum(m.ag for m in ms) / len(ms); mu = (avg_h + avg_a) / 2
    gf, ga, n = {}, {}, {}
    for m in ms:
        for t, f, a in ((m.home, m.hg, m.ag), (m.away, m.ag, m.hg)):
            gf[t] = gf.get(t, 0) + f; ga[t] = ga.get(t, 0) + a; n[t] = n.get(t, 0) + 1
    att = {t: (gf[t] + shrink * mu) / (n[t] + shrink) / mu for t in n}
    dfn = {t: (ga[t] + shrink * mu) / (n[t] + shrink) / mu for t in n}
    return M0Fit(avg_h, avg_a, att, dfn, n)

def rates_m0(f: M0Fit, home: str, away: str, min_matches: int = 5):
    for t in (home, away):
        if f.n.get(t, 0) < min_matches: return InsufficientData(f"{t} has {f.n.get(t, 0)} matches")
    return f.avg_home * f.att[home] * f.dfn[away], f.avg_away * f.att[away] * f.dfn[home]
