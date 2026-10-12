"""Scoreline grid and derived markets. Floats allowed here (statistical code)."""
import numpy as np
from scipy.stats import poisson

CAP = 10

def grid(lh: float, la: float, rho: float = 0.0) -> np.ndarray:
    if lh <= 0 or la <= 0:
        raise ValueError("expected goals must be positive")
    g = np.outer(poisson.pmf(range(CAP + 1), lh), poisson.pmf(range(CAP + 1), la))
    if rho:
        g[0, 0] *= 1 - lh * la * rho
        g[0, 1] *= 1 + lh * rho
        g[1, 0] *= 1 + la * rho
        g[1, 1] *= 1 - rho
        if (g < 0).any():
            raise ValueError("rho out of valid range for these rates")
    retained = g.sum()
    if retained < 0.9999:
        raise ValueError(f"retained mass {retained:.6f} below 0.9999")
    return g / retained

def markets(g: np.ndarray) -> dict:
    i, j = np.indices(g.shape)
    home, draw, away = g[i > j].sum(), g[i == j].sum(), g[i < j].sum()
    totals = i + j
    ou = {f"{l}": {"over": float(g[totals > l].sum()), "under": float(g[totals < l].sum())}
          for l in (0.5, 1.5, 2.5, 3.5, 4.5)}
    btts = float(g[(i > 0) & (j > 0)].sum())
    return {"1x2": {"home": float(home), "draw": float(draw), "away": float(away)},
            "double_chance": {"1x": float(home + draw), "12": float(home + away), "x2": float(draw + away)},
            "over_under": ou, "btts": {"yes": btts, "no": float(1 - btts)}}

def correct_score(g: np.ndarray, top: int = 5):
    idx = np.dstack(np.unravel_index(np.argsort(-g, axis=None), g.shape))[0][:top]
    return [(int(a), int(b), float(g[a, b])) for a, b in idx]
