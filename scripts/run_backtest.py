"""Generates docs/MODEL_REPORT.md from a real backtest run. Data source is chosen explicitly.
Usage: python scripts/run_backtest.py synthetic   (no real data available in this environment)"""
import sys, random
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parents[1] / "backend"))
from app.engine.backtest import walk_forward
from app.engine.dixon_coles import Match
from app.engine.metrics import *

def synthetic(seed=42, teams=12):
    rng = np.random.default_rng(seed); names = [f"T{i:02d}" for i in range(teams)]
    att = rng.normal(0, .25, teams); dfn = rng.normal(0, .25, teams); out = []; day = datetime(2023, 8, 1)
    pairs = [(i, j) for i in range(teams) for j in range(teams) if i != j] * 2
    random.Random(seed).shuffle(pairs)
    for k, (i, j) in enumerate(pairs):
        out.append(Match(day + timedelta(days=k * 300 // len(pairs)), names[i], names[j],
                         int(rng.poisson(np.exp(.1 + .3 + att[i] + dfn[j]))), int(rng.poisson(np.exp(.1 + att[j] + dfn[i])))))
    return out

def main(source):
    if source != "synthetic": sys.exit("only 'synthetic' is available until real CSV history is supplied")
    data = synthetic(); rows, skipped = walk_forward(data)
    y = np.array([r["y"] for r in rows]); P = {k: np.array([r[k] for r in rows]) for k in ("uniform", "base_rate", "m0", "m1")}
    L = ["# Model report", "", "> **SYNTHETIC DATA.** Matches are simulated from known team strengths (seed 42). This validates the",
         "> harness and shows the models can recover signal. It says nothing about accuracy on real football or about profit.",
         "> Market-odds benchmark: NOT EVALUATED (no historical odds in this run).", "",
         f"Matches generated: {len(data)}. Predictions evaluated: {len(rows)}. Skipped (insufficient data): {skipped}.",
         "Walk-forward, expanding window, refit every 21 days, features strictly before each cutoff. 95% bootstrap CIs (1000 resamples, seed 0).", "",
         "| Model | Log loss | Brier | RPS | Sharpness | ECE |", "|---|---|---|---|---|---|"]
    for k, name in (("uniform", "Uniform"), ("base_rate", "League base rate"), ("m0", "M0 Poisson"), ("m1", "M1 Dixon-Coles")):
        ll, br, rp = (bootstrap_ci(f(P[k], y)) for f in (logloss_each, brier_each, rps_each))
        fmt = lambda t: f"{t[0]:.4f} [{t[1]:.4f}, {t[2]:.4f}]"
        L.append(f"| {name} | {fmt(ll)} | {fmt(br)} | {fmt(rp)} | {sharpness(P[k]):.3f} | {calibration(P[k], y)[1]:.4f} |")
    d = logloss_each(P["m1"], y) - logloss_each(P["m0"], y); m, lo, hi = bootstrap_ci(d)
    verdict = "M1 is better than M0 (CI excludes zero)" if hi < 0 else ("M1 is worse than M0 (CI excludes zero)" if lo > 0 else "no distinguishable difference between M1 and M0 (CI includes zero)")
    L += ["", f"Paired log-loss difference M1 minus M0: {m:.4f} [{lo:.4f}, {hi:.4f}] — {verdict}.", "",
          "## M1 calibration (pooled outcome probabilities)", "", "| Mean predicted | Observed frequency | n |", "|---|---|---|"]
    L += [f"| {a:.3f} | {b:.3f} | {n} |" for a, b, n in calibration(P["m1"], y)[0]]
    L += ["", "M2 (scikit-learn) was not built, so no adoption test was run."]
    Path(__file__).parents[1].joinpath("docs/MODEL_REPORT.md").write_text("\n".join(L) + "\n"); print("\n".join(L[:16]))

main(sys.argv[1] if len(sys.argv) > 1 else "synthetic")
