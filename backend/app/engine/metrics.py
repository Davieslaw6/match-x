import numpy as np
# outcomes indexed 0=home, 1=draw, 2=away; P is (n,3), y is (n,) ints
def logloss_each(P, y): return -np.log(np.clip(P[np.arange(len(y)), y], 1e-12, 1))
def brier_each(P, y): O = np.eye(3)[y]; return ((P - O) ** 2).sum(axis=1)
def rps_each(P, y):
    O = np.eye(3)[y]; return (((np.cumsum(P, 1) - np.cumsum(O, 1))[:, :2]) ** 2).sum(axis=1) / 2
def sharpness(P): return float(P.max(axis=1).mean())

def calibration(P, y, bins=10):
    """Pooled reliability over all three outcome probabilities. Returns (rows, ECE)."""
    p = P.ravel(); o = np.eye(3)[y].ravel(); edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1); rows, ece = [], 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            rows.append((float(p[m].mean()), float(o[m].mean()), int(m.sum()))); ece += m.sum() / len(p) * abs(p[m].mean() - o[m].mean())
    return rows, float(ece)

def bootstrap_ci(values, B=1000, seed=0, alpha=0.05):
    v = np.asarray(values, float); rng = np.random.default_rng(seed)
    means = v[rng.integers(0, len(v), (B, len(v)))].mean(axis=1)
    return float(v.mean()), float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))
