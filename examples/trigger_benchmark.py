#!/usr/bin/env python3
"""Score skill *discovery* on its own, with no reference to output quality.

A skill has two halves that fail independently: a description that has to match
the user's phrasing, and content that has to improve the answer once loaded. The
A/B report measures the product of the two, which means a good skill with a bad
description and a bad skill with a good description produce the same number. This
benchmark isolates the first half. It reads only the arm-B manifest — no answers,
no rubrics — so nothing about the generated code can flatter or spoil the result.

Same 16 tasks. For every arm-B run it asks four questions: did the intended skill
fire, did an unintended one fire, did several fire, did nothing fire.

Definitions, spelled out because a precision figure whose denominator a reader has
to reverse-engineer is not a result:

  Unit of analysis  one arm-B run. Ten skills are installed in every run, so each
                    run is one retrieval attempt against a ten-item catalogue.
  Intended skill    `skill` in tasks.py. Read from there, never re-listed here.
  Scored set        the 13 positive and trap tasks. On a trap the intended skill
                    is exactly the text that says "this should not be an agent",
                    so firing it is the wanted behaviour, same as a positive.
  TP                a run where the intended skill fired.
  FP                each skill load that was not the intended skill. A run that
                    loads two unintended skills contributes two.
  FN                a run where the intended skill did not fire. One per run.
  precision         TP / (TP + FP). Denominator: every skill load on the scored
                    set. "Of all the skills the agent chose to read, what share
                    were the right one."
  recall            TP / (TP + FN) = TP / runs. Denominator: scored-set runs, not
                    loads. "Of the runs where a skill should have fired, what
                    share fired it." Loading the intended skill plus a spurious
                    one still counts as recalled — and is penalised in precision.
  F1                harmonic mean of the two.
  no-trigger rate   runs where nothing fired / all arm-B runs.
  wrong-trigger rate runs where at least one load was not the intended skill /
                    all arm-B runs.

The three controls are kept out of precision and recall and reported separately.
On a control the correct behaviour is not to apply the skill, so firing nothing
is a pass, not a miss; and because every skill carries a "when to break the
rules" section, loading the task's own skill and then restraining yourself is
defensible too. Only an unrelated skill firing is a failure there. Counting a
control's silence as a missed trigger would score the descriptions as broken for
behaving exactly as designed — which is the kind of accounting that makes a
benchmark useless in the direction that flatters nobody.

  python3 examples/trigger_benchmark.py
"""
from __future__ import annotations
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "graders")); sys.path.insert(0, str(ROOT / "tasks"))
import triggering as tg             # noqa: E402
from tasks import TASKS             # noqa: E402

SKILL_NAMES = sorted(p.parent.name for p in ROOT.parent.glob("*/SKILL.md"))


def load(runs: pathlib.Path, arm: str = "b") -> list[dict]:
    mf = runs / f"manifest_{arm}.jsonl"
    if not mf.exists():
        return []
    return [json.loads(l) for l in mf.read_text(encoding="utf-8").splitlines() if l.strip()]


def pct(num: int, den: int) -> str:
    return "—" if not den else f"{100*num/den:.0f}%"


def ratio(num: int, den: int) -> float | None:
    return None if not den else num / den


def fmt(x: float | None) -> str:
    return "—" if x is None else f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="score skill discovery, independent of output quality")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"),
                    help="where manifest_b.jsonl lives")
    ap.add_argument("--out", default=str(ROOT / "TRIGGERING.md"))
    args = ap.parse_args()
    runs = pathlib.Path(args.runs_dir)

    rows = [r for r in load(runs, "b") if r.get("task") in {t["id"] for t in TASKS}]
    if not rows:
        print(f"no arm-B runs recorded under {runs} — nothing to score", file=sys.stderr)
        return 1

    per_task: dict[str, list[dict]] = {t["id"]: [] for t in TASKS}
    for r in rows:
        per_task[r["task"]].append(r)

    tp = fp = fn = 0                       # scored set: positives + traps
    ctl_none = ctl_own = ctl_wrong = 0      # controls, on their own terms
    ctl_fp = 0                             # unrelated loads on controls
    n_none = n_wrong = n_multi = 0          # whole suite
    table = []

    for t in TASKS:
        tid = t["id"]
        brs = per_task[tid]
        if not brs:
            continue
        want = tg.expected_skill(tid)
        c_intended = c_wrong = c_multi = c_none = 0
        t_tp = t_fp = t_fn = 0
        for r in brs:
            got = tg.fired_skills(r)
            hit = want in got
            if not got:
                c_none += 1
                n_none += 1
            else:
                if len(got) > 1:
                    c_multi += 1
                    n_multi += 1
                if not hit:
                    c_wrong += 1
                if not hit or len(got) > 1:
                    n_wrong += 1
            if hit:
                c_intended += 1
            if tg.trigger_required(tid):
                t_tp += 1 if hit else 0
                t_fn += 0 if hit else 1
                t_fp += len(got) - (1 if hit else 0)
            else:
                unrelated = [s for s in got if s != want]
                ctl_fp += len(unrelated)
                if not got:
                    ctl_none += 1
                elif unrelated:
                    ctl_wrong += 1
                else:
                    ctl_own += 1
        tp, fp, fn = tp + t_tp, fp + t_fp, fn + t_fn
        table.append(dict(id=tid, kind=t["kind"], want=want, n=len(brs),
                          intended=c_intended, wrong=c_wrong, multi=c_multi, none=c_none,
                          recall=ratio(t_tp, len(brs)) if tg.trigger_required(tid) else None))

    scored_runs = sum(r["n"] for r in table if tg.trigger_required(r["id"]))
    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall and (precision + recall) else None)
    precision_all = ratio(tp, tp + fp + ctl_fp)

    L = ["# Triggering benchmark", "",
         "Generated by `examples/trigger_benchmark.py`. Scores skill **discovery** only: it "
         "reads the arm-B manifest and never looks at a generated answer, so output quality "
         "cannot move these numbers. A skill whose description never matches is worth zero in "
         "production however good its content is, and the A/B report alone cannot tell the two "
         "failures apart.", "",
         f"**{len(rows)} arm-B run(s)** across {sum(1 for r in table)} task(s); "
         f"{len(SKILL_NAMES)} skills installed in each.", "",
         "## Definitions", "",
         "One arm-B run is one retrieval attempt against the installed catalogue. The intended "
         "skill per task is the `skill` field in `tasks.py`.", "",
         "| term | definition | denominator |", "|---|---|---|",
         "| TP | the intended skill fired in that run | — |",
         "| FP | a skill load that was not the intended skill (two spurious loads count twice) | — |",
         "| FN | the intended skill did not fire in that run | — |",
         "| precision | TP / (TP + FP) | every skill load on the scored set |",
         "| recall | TP / (TP + FN) | every run in the scored set |",
         "| no-trigger rate | runs where nothing fired | all arm-B runs |",
         "| wrong-trigger rate | runs with at least one unintended load | all arm-B runs |",
         "",
         "The **scored set** is the 10 positives and 3 traps. On a trap the intended skill is "
         "the text that says \"this is a workflow, not an agent\", so firing it is wanted, "
         "exactly as on a positive. The **3 controls are excluded** from precision and recall: "
         "there the correct behaviour is not to apply the skill, so silence is a pass and not a "
         "miss, and loading the task's own skill is defensible because every skill documents "
         "when not to apply itself. Only an unrelated skill firing on a control is a failure, "
         "and it is counted below.", "",
         "## Headline", "", "```",
         f"scored set          {scored_runs} run(s) over "
         f"{sum(1 for r in table if tg.trigger_required(r['id']))} task(s)",
         f"TP / FP / FN        {tp} / {fp} / {fn}",
         f"precision           {fmt(precision)}",
         f"recall              {fmt(recall)}",
         f"F1                  {fmt(f1)}",
         "",
         f"no-trigger rate     {pct(n_none, len(rows)):>4}   ({n_none}/{len(rows)} runs, whole suite)",
         f"wrong-trigger rate  {pct(n_wrong, len(rows)):>4}   ({n_wrong}/{len(rows)} runs, whole suite)",
         f"multi-fire runs     {pct(n_multi, len(rows)):>4}   ({n_multi}/{len(rows)} runs)",
         "",
         f"precision incl. controls  {fmt(precision_all)}  (adds {ctl_fp} unrelated load(s) on "
         "controls to FP; a control's own skill counts neither way)",
         "```", ""]

    if not scored_runs:
        L += ["No positive or trap task has an arm-B run yet, so precision and recall have no "
              "denominator. The per-task table below is the whole of what exists.", ""]
    elif tp == 0:
        L += ["**The intended skill never fired on the scored set.** Every arm-B score in "
              "`RESULTS.md` therefore measures the descriptions, not the content. A null result "
              "in the A/B is a finding about triggering until this number moves.", ""]

    L += ["## Per task", "",
          "| task | kind | intended skill | runs | intended fired | wrong fired | multiple fired | nothing fired | recall |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in table:
        note = "" if tg.trigger_required(r["id"]) else " *(none wanted)*"
        L.append(f"| {r['id']} | {r['kind']} | {r['want']}{note} | {r['n']} | "
                 f"{r['intended']} | {r['wrong']} | {r['multi']} | {r['none']} | "
                 f"{fmt(r['recall'])} |")

    ctl_runs = ctl_none + ctl_own + ctl_wrong
    L += ["", "## Controls", "",
          "Not scored above. Reported because over-triggering is the most plausible way these "
          "skills are actually harmful, and a discovery benchmark that only rewards firing "
          "would recommend exactly that.", ""]
    if not ctl_runs:
        L += ["No control task has an arm-B run yet.", ""]
    else:
        L += ["| control outcome | runs | share |", "|---|---|---|",
              f"| nothing fired (clean pass) | {ctl_none} | {pct(ctl_none, ctl_runs)} |",
              f"| the task's own skill fired (allowed — see its \"when to break the rules\") | "
              f"{ctl_own} | {pct(ctl_own, ctl_runs)} |",
              f"| an unrelated skill fired (over-trigger) | {ctl_wrong} | "
              f"{pct(ctl_wrong, ctl_runs)} |", "",
              "Whether the `own skill fired` runs stayed restrained is a *score* question, and "
              "the control rows of `RESULTS.md` answer it. High scores there with a fired skill "
              "is the best possible outcome: the skill was read and correctly not applied.", ""]

    L += ["## What this does not measure", "",
          "- Nothing here reflects answer quality. A perfect trigger rate with useless content "
          "scores 1.00 on this page.",
          "- Firing is detected from the transcript — a `Skill` tool call, or a read of a "
          "`SKILL.md`. A session that glanced at a description and proceeded without loading "
          "the file counts as not fired, so these numbers are a floor.",
          "- Ten skills are installed together, so the descriptions compete. A skill that "
          "triggers reliably in isolation can lose to a neighbour here; that is the production "
          "condition, and the reason the eval installs all ten.",
          "- With a handful of runs per task, a single task's recall is 0, 0.33, 0.67 or 1.00. "
          "Read the suite totals, not a row.", ""]

    dest = pathlib.Path(args.out)
    dest.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {dest}")
    print(f"runs={len(rows)}  scored={scored_runs}  TP/FP/FN={tp}/{fp}/{fn}")
    print(f"precision={fmt(precision)}  recall={fmt(recall)}  F1={fmt(f1)}")
    print(f"no-trigger={pct(n_none, len(rows))}  wrong-trigger={pct(n_wrong, len(rows))}  "
          f"multi-fire={pct(n_multi, len(rows))}")
    if ctl_runs:
        print(f"controls: {ctl_none} silent / {ctl_own} own skill / {ctl_wrong} over-triggered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
