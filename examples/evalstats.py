"""Small-sample statistics for the A/B report: bootstrap CI, effect size, win/tie/loss.

A mean delta over three runs is a number, not evidence. This module exists so
RESULTS.md can state how uncertain its own headline is, in the same file as the
headline, instead of leaving a reader to assume +0.16 means something.

Stdlib only, deliberately: the harness must run with no install step, and a
percentile bootstrap needs nothing numpy has. The seed and the resample count
are constants here and are printed into the report, so anyone re-running
report.py over the same manifests reproduces the interval to the last digit.

The resampling unit is the TASK, not the run. Runs of one task share a prompt
and a rubric, so they are not independent draws and resampling them would
shrink the interval by counting one task several times. And because the 16 tasks
were hand-picked rather than sampled, the interval covers uncertainty from the
task mix and from run noise only — not from any population of "all coding
tasks". Saying that out loud is cheaper than being caught implying otherwise.
"""
from __future__ import annotations
import random, statistics as st

BOOTSTRAP_ITERS = 10_000
BOOTSTRAP_SEED = 20260201        # fixed: a published interval that moves per run is not a result
CI_LEVEL = 0.95

# Below this many paired tasks a bootstrap is theatre — resampling two numbers
# returns those two numbers — so callers print the reason instead of an interval.
MIN_BOOTSTRAP_N = 3
# Above MIN but still thin. The report keeps the interval and flags it.
THIN_BOOTSTRAP_N = 6

# A rubric score is the mean of a handful of binary checks, so the granularity is
# coarse: one check on the widest rubric (7 checks) is 0.14, and on the narrowest
# (1 check) it is 1.00. Any delta produced by a *consistent* difference between
# the arms is therefore at least 0.14. A per-task mean delta under 0.05 can only
# come from a single check flipping in a minority of runs, which at n<=5 is noise,
# not a win. Exact ties are also common, and this absorbs float dust for free.
TIE_TOLERANCE = 0.05


def _quantile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated quantile. Only ever fed the sorted bootstrap means."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def bootstrap_ci_mean(values, *, iters: int = BOOTSTRAP_ITERS,
                      seed: int = BOOTSTRAP_SEED,
                      level: float = CI_LEVEL) -> tuple[float, float] | None:
    """Percentile bootstrap CI for the mean. None when there is nothing to resample.

    Returning None rather than a degenerate [x, x] matters: the harness gets run
    at n=1 first, and an interval of zero width reads as certainty.
    """
    vals = [float(v) for v in values]
    if len(vals) < MIN_BOOTSTRAP_N:
        return None
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(sum(rng.choices(vals, k=n)) / n for _ in range(iters))
    tail = (1.0 - level) / 2.0
    return _quantile(means, tail), _quantile(means, 1.0 - tail)


def cohens_dz(deltas) -> float | None:
    """Paired standardised mean difference: mean(delta) / sd(delta) across tasks.

    Paired because every task is measured in both arms, so d_z is the effect size
    that matches how the delta was computed. None when it is undefined: fewer than
    two deltas, or zero spread (every task moved by exactly the same amount, which
    with coarse rubric scores happens more often than it should).
    """
    ds = [float(d) for d in deltas]
    if len(ds) < 2:
        return None
    sd = st.stdev(ds)
    return None if sd == 0 else st.mean(ds) / sd


def cliffs_delta(a, b) -> float | None:
    """P(b > a) - P(a > b) over run scores. None if either arm has no runs.

    Distribution-free and bounded in [-1, 1], which is why it is worth reporting
    next to d_z: rubric scores are means of binary checks on a 0-1 scale, clumped
    and nowhere near normal, and d_z assumes a spread that small samples of such
    scores do not really have.
    """
    xs, ys = list(a), list(b)
    if not xs or not ys:
        return None
    gt = sum(1 for y in ys for x in xs if y > x)
    lt = sum(1 for y in ys for x in xs if y < x)
    return (gt - lt) / (len(xs) * len(ys))


def cliff_label(d: float | None) -> str:
    """Romano et al. thresholds. Named so nobody has to look up what 0.33 means."""
    if d is None:
        return "undefined"
    m = abs(d)
    if m < 0.147:
        return "negligible"
    if m < 0.33:
        return "small"
    if m < 0.474:
        return "medium"
    return "large"


def classify(delta: float | None, tol: float = TIE_TOLERANCE) -> str | None:
    """win / tie / loss for one task, by the documented tolerance."""
    if delta is None:
        return None
    if abs(delta) < tol:
        return "tie"
    return "win" if delta > 0 else "loss"


def wtl(deltas, tol: float = TIE_TOLERANCE) -> dict[str, int]:
    counts = {"win": 0, "tie": 0, "loss": 0}
    for d in deltas:
        k = classify(d, tol)
        if k:
            counts[k] += 1
    return counts
