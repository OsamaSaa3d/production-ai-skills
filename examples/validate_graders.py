#!/usr/bin/env python3
"""Validate every rubric against its naive/skilled fixture pair.

A grader nobody tested is a number nobody should trust. This runs offline, needs
no API key, and fails if any rubric does not separate the pair — which would mean
that task's rubric is measuring nothing.
"""
from __future__ import annotations
import pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "graders")); sys.path.insert(0, str(ROOT / "tasks"))
import rubrics                                   # noqa: E402
from tasks import BY_ID, TASKS                   # noqa: E402

# On a control the correct behaviour is NOT applying the skill, so the restrained
# answer is the one that should score high and the over-applied one is the failure.
# (good_suffix, bad_suffix) per task; everything else is the default pair.
PAIRS = {"t08": ("naive", "overapplied"), "t12": ("naive", "overapplied")}
DEFAULT_PAIR = ("skilled", "naive")
MIN_SEPARATION = 0.40


def main() -> int:
    rows, failures = [], []
    for t in TASKS:
        tid = t["id"]
        good_sfx, bad_sfx = PAIRS.get(tid, DEFAULT_PAIR)
        good = ROOT / "fixtures" / f"{tid}_{good_sfx}.md"
        bad = ROOT / "fixtures" / f"{tid}_{bad_sfx}.md"
        if not good.exists() or not bad.exists():
            failures.append(f"{tid}: missing fixture pair "
                            f"({good.name} / {bad.name})"); continue
        hi = rubrics.grade(tid, good.read_text())["score"]
        lo = rubrics.grade(tid, bad.read_text())["score"]
        rows.append((tid, t["kind"], (bad_sfx, good_sfx), lo, hi, hi - lo))
        if hi - lo < MIN_SEPARATION:
            failures.append(f"{tid}: separation {hi-lo:+.2f} < {MIN_SEPARATION}")

    print(f"{'task':<6}{'kind':<10}{'low':>7}{'high':>7}{'sep':>8}   fixtures")
    for tid, kind, labels, lo, hi, sep in rows:
        print(f"{tid:<6}{kind:<10}{lo:>7.2f}{hi:>7.2f}{sep:>+8.2f}   {labels[0]} vs {labels[1]}")
    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        return 1
    print(f"all {len(rows)} rubrics separate their fixture pair by >= {MIN_SEPARATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
