# Model report

> **SYNTHETIC DATA.** Matches are simulated from known team strengths (seed 42). This validates the
> harness and shows the models can recover signal. It says nothing about accuracy on real football or about profit.
> Market-odds benchmark: NOT EVALUATED (no historical odds in this run).

Matches generated: 264. Predictions evaluated: 142. Skipped (insufficient data): 17.
Walk-forward, expanding window, refit every 21 days, features strictly before each cutoff. 95% bootstrap CIs (1000 resamples, seed 0).

| Model | Log loss | Brier | RPS | Sharpness | ECE |
|---|---|---|---|---|---|
| Uniform | 1.0986 [1.0986, 1.0986] | 0.6667 [0.6667, 0.6667] | 0.2379 [0.2261, 0.2496] | 0.333 | 0.0000 |
| League base rate | 1.0831 [1.0236, 1.1384] | 0.6570 [0.6146, 0.6965] | 0.2368 [0.2192, 0.2554] | 0.503 | 0.0457 |
| M0 Poisson | 1.0567 [0.9884, 1.1238] | 0.6353 [0.5878, 0.6818] | 0.2269 [0.2065, 0.2494] | 0.492 | 0.0506 |
| M1 Dixon-Coles | 1.0666 [0.9928, 1.1399] | 0.6416 [0.5906, 0.6916] | 0.2288 [0.2070, 0.2515] | 0.510 | 0.0395 |

Paired log-loss difference M1 minus M0: 0.0099 [-0.0070, 0.0274] — no distinguishable difference between M1 and M0 (CI includes zero).

## M1 calibration (pooled outcome probabilities)

| Mean predicted | Observed frequency | n |
|---|---|---|
| 0.083 | 0.250 | 4 |
| 0.167 | 0.239 | 71 |
| 0.248 | 0.266 | 143 |
| 0.344 | 0.330 | 88 |
| 0.449 | 0.396 | 53 |
| 0.547 | 0.500 | 38 |
| 0.635 | 0.632 | 19 |
| 0.740 | 0.556 | 9 |
| 0.801 | 0.000 | 1 |

M2 (scikit-learn) was not built, so no adoption test was run.
