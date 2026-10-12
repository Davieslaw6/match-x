"""M1 Dixon-Coles with exponential time decay, ridge identifiability. Pure function of rows before cutoff."""
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

@dataclass(frozen=True)
class Match:
    kickoff: datetime
    home: str
    away: str
    hg: int
    ag: int

@dataclass(frozen=True)
class InsufficientData:
    reason: str

@dataclass(frozen=True)
class Fit:
    attack: dict
    defence: dict
    home_adv: float
    rho: float
    teams_matches: dict

def fit(matches: list[Match], cutoff: datetime, xi: float = 0.003, min_matches: int = 8,
        ridge: float = 0.05):
    ms = [m for m in matches if m.kickoff < cutoff]  # strict: leakage guard
    counts: dict = {}
    for m in ms:
        for t in (m.home, m.away):
            counts[t] = counts.get(t, 0) + 1
    if len(ms) < 20 or not counts:
        return InsufficientData(f"only {len(ms)} matches before cutoff")
    teams = sorted(counts)
    ix = {t: k for k, t in enumerate(teams)}
    n = len(teams)
    h = np.array([ix[m.home] for m in ms]); a = np.array([ix[m.away] for m in ms])
    hg = np.array([m.hg for m in ms]); ag = np.array([m.ag for m in ms])
    age = np.array([(cutoff - m.kickoff).total_seconds() / 86400 for m in ms])
    w = np.exp(-xi * age)

    def nll(p):
        att, dfn, ha, rho = p[:n], p[n:2 * n], p[2 * n], p[2 * n + 1]
        lh, la = np.exp(att[h] + dfn[a] + ha), np.exp(att[a] + dfn[h])
        ll = hg * np.log(lh) - lh - gammaln(hg + 1) + ag * np.log(la) - la - gammaln(ag + 1)
        tau = np.ones(len(ms))
        m00 = (hg == 0) & (ag == 0); m01 = (hg == 0) & (ag == 1)
        m10 = (hg == 1) & (ag == 0); m11 = (hg == 1) & (ag == 1)
        tau[m00] = 1 - lh[m00] * la[m00] * rho; tau[m01] = 1 + lh[m01] * rho
        tau[m10] = 1 + la[m10] * rho; tau[m11] = 1 - rho
        ll += np.log(np.clip(tau, 1e-9, None))
        return -(w * ll).sum() + ridge * (att @ att + dfn @ dfn)

    x0 = np.zeros(2 * n + 2); x0[2 * n] = 0.25
    bounds = [(None, None)] * (2 * n) + [(None, None), (-0.2, 0.2)]
    r = minimize(nll, x0, method="L-BFGS-B", bounds=bounds)
    if not r.success:
        return InsufficientData(f"optimiser failed: {r.message}")
    p = r.x
    return Fit({t: float(p[ix[t]]) for t in teams}, {t: float(p[n + ix[t]]) for t in teams},
               float(p[2 * n]), float(p[2 * n + 1]), counts)

def rates(f: Fit, home: str, away: str, min_matches: int = 8):
    for t in (home, away):
        if f.teams_matches.get(t, 0) < min_matches:
            return InsufficientData(f"{t} has {f.teams_matches.get(t, 0)} matches, need {min_matches}")
    return (float(np.exp(f.attack[home] + f.defence[away] + f.home_adv)),
            float(np.exp(f.attack[away] + f.defence[home])))
