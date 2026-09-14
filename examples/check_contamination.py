#!/usr/bin/env python3
"""Verify arm A never saw the skills.

This is the control the whole comparison rests on. If an arm-A session read a
SKILL.md — deliberately or because it wandered into the repo — that run is not a
control and must be discarded. An agent asked to write tool-calling code, sitting
anywhere near a repo full of tool-calling guidance, will plausibly read it.

Checks three things:
  1. no arm-A transcript mentions a skill file path or a skill directory name
  2. no arm-A answer reproduces distinctive skill phrasing
  3. arm B recorded a skill_triggered value at least sometimes (if it never fired,
     the treatment was never applied and any null result is about the descriptions)

Exit 1 if any arm-A run looks contaminated.
"""
from __future__ import annotations
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent

SKILL_NAMES = sorted(p.parent.name for p in REPO.glob("*/SKILL.md"))

# Phrases distinctive enough that reproducing one suggests the text was read,
# not independently invented. Kept short and specific on purpose.
TELLS = [
    r"SKILL\.md",
    r"\breferences/[a-z-]+\.md",
    r"escalation ladder",
    r"poka-?yoke",
    r"agent-computer interface",
    r"altitude.{0,20}(heuristic|Goldilocks)",
    r"high-signal tokens",
]


def load(arm: str) -> list[dict]:
    mf = ROOT / "runs" / f"manifest_{arm}.jsonl"
    if not mf.exists():
        return []
    return [json.loads(l) for l in mf.read_text().splitlines() if l.strip()]


def main() -> int:
    a_rows, b_rows = load("a"), load("b")
    if not a_rows:
        print("no arm-A runs recorded yet", file=sys.stderr)
        return 1

    name_re = re.compile("|".join(rf"\b{re.escape(n)}\b" for n in SKILL_NAMES), re.I)
    tell_re = re.compile("|".join(TELLS), re.I)

    bad = []
    for row in a_rows:
        hits = set()
        for sub, label in ((ROOT / "runs" / "a", "answer"),
                           (ROOT / "runs" / "transcripts" / "a", "transcript")):
            p = sub / row["file"]
            if not p.exists():
                continue
            text = p.read_text()
            if name_re.search(text):
                hits.add(f"{label}: names a skill directory")
            if tell_re.search(text):
                hits.add(f"{label}: reproduces distinctive skill phrasing")
        if hits:
            bad.append((row["task"], row["run"], row["file"], sorted(hits)))

    print(f"arm A runs checked: {len(a_rows)}")
    for task, run, fn, hits in bad:
        print(f"  CONTAMINATED {task} run{run} ({fn})")
        for h in hits:
            print(f"      {h}")

    triggered = [r for r in b_rows if r.get("skill_triggered")]
    if b_rows:
        pct = 100 * len(triggered) / len(b_rows)
        print(f"\narm B runs: {len(b_rows)}   skill fired in {len(triggered)} ({pct:.0f}%)")
        if not triggered:
            print("  WARNING: the skill never fired in arm B. The treatment was never")
            print("  applied, so a null result here is a finding about the skill")
            print("  descriptions, not about the skill content. Report it that way.")

    if bad:
        print(f"\n{len(bad)} arm-A run(s) contaminated. Discard and re-run them in a")
        print("clean directory with no path to this repository.")
        return 1
    print("\nno contamination detected in arm A")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
