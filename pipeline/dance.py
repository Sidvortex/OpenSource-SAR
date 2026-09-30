"""
The dance classifier, v1 (rules). Mirrors web/src/dance.ts exactly; both must pass
data/dance_tests.json:  python pipeline/dance.py --test

Given a time series (days, values, 1-sigma noise) it answers one question: which
of five simple patterns explains the change best, measured against the noise?
  still      changes stay within the noise
  tango      one sudden jump explains the change far better than a trend
  waltz      a rise and a fall (or fall and rise) inside the period
  crescendo  a trend that keeps speeding up
  march      a steady trend
"""
import json
import sys
from pathlib import Path

import numpy as np


def _median(values):
    return float(np.median(values))


def _num(v, unit):
    digits = 0 if abs(v) >= 10 else 1
    return f"{v:+.{digits}f}{(' ' + unit) if unit else ''}"


def classify(t, y, sigma=None, unit="", when=None):
    """when: optional display labels for each point, e.g. dates, used in the reason text."""
    labels = list(when) if when is not None else [f"day {v:.0f}" for v in t]
    t, y = np.asarray(t, float), np.asarray(y, float)
    keep = np.isfinite(y)
    labels = [l for l, k in zip(labels, keep) if k]
    sig = np.broadcast_to(np.asarray(sigma if sigma is not None else np.nan, float), y.shape)[keep]
    t, y = t[keep], y[keep]
    n = len(y)
    if n < 3:
        return {"dance": "still", "confidence": "low", "reason": "Too few measurements to tell yet."}
    finite_sig = sig[np.isfinite(sig) & (sig > 0)]
    noise = _median(finite_sig) if finite_sig.size else _median(np.abs(np.diff(y))) / 0.6745 / np.sqrt(2)
    noise = max(noise, 1e-9)
    amp = float(y.max() - y.min())
    if amp < 3 * noise:
        return {"dance": "still", "confidence": "high", "reason": "Every change stays within the measurement noise."}
    span = float(t[-1] - t[0]) or 1.0
    x = (t - t[0]) / span
    lin = np.polyfit(x, y, 1)
    rss_lin = float(np.sum((np.polyval(lin, x) - y) ** 2))
    quad = np.polyfit(x, y, 2)
    rss_quad = float(np.sum((np.polyval(quad, x) - y) ** 2))
    best_k, rss_step, jump = 1, np.inf, 0.0
    for k in range(1, n):
        a, b = y[:k].mean(), y[k:].mean()
        rss = float(np.sum((y[:k] - a) ** 2) + np.sum((y[k:] - b) ** 2))
        if rss < rss_step:
            best_k, rss_step, jump = k, rss, float(b - a)
    confidence = "high" if amp > 10 * noise else "medium"
    floor = n * noise ** 2                     # residuals this small are just noise
    if abs(jump) > 4 * noise and rss_step < 0.35 * max(rss_lin, floor) and rss_step < 0.5 * max(rss_quad, floor):
        return {"dance": "tango", "confidence": confidence,
                "reason": f"A sudden change of {_num(jump, unit)} between {labels[best_k - 1]} and {labels[best_k]}.",
                "jump": jump, "at": [float(t[best_k - 1]), float(t[best_k])]}
    c2, c1 = float(quad[0]), float(quad[1])
    if rss_quad < 0.6 * max(rss_lin, floor) and abs(c2) * 0.25 > 1.5 * noise:
        vertex = -c1 / (2 * c2) if c2 else -1.0
        if 0.15 < vertex < 0.85:
            shape = "rose and then fell" if c2 < 0 else "fell and then rose"
            return {"dance": "waltz", "confidence": confidence, "reason": f"It {shape} within the period, like a seasonal cycle."}
        slope_start, slope_end = c1, c1 + 2 * c2
        if abs(slope_end) > abs(slope_start) and np.sign(slope_end) == np.sign(lin[0]):
            return {"dance": "crescendo", "confidence": confidence, "reason": "The change keeps getting faster."}
    per_12_days = float(lin[0]) / span * 12
    if abs(lin[0]) > 3 * noise:
        return {"dance": "march", "confidence": confidence,
                "reason": f"A steady trend of about {_num(per_12_days, unit)} every 12 days.", "rate_per_12_days": per_12_days}
    return {"dance": "still", "confidence": "medium", "reason": "No clear pattern beyond the noise."}


def run_tests():
    cases = json.loads((Path(__file__).resolve().parents[1] / "data" / "dance_tests.json").read_text())["cases"]
    failed = 0
    for case in cases:
        got = classify(case["t"], case["y"], case["sigma"])["dance"]
        ok = got == case["expected"]
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {case['name']:<26} expected {case['expected']:<10} got {got}")
    print(f"{len(cases) - failed}/{len(cases)} passed")
    return failed


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(1 if run_tests() else 0)
    print(__doc__)
