#!/usr/bin/env python3
"""Build examples/RESULTS.md from the manifests and results.tsv.

Reports per task, never aggregate-only: a change that lifts the mean while
breaking two tasks is a different decision, and the aggregate hides it.

Reports uncertainty beside every aggregate. At n=3 a delta of +0.16 is
interesting and is not evidence, so the headline carries a bootstrap interval,
an effect size, a median and a win/tie/loss count — and says plainly when there
are too few runs for any of them to mean anything, rather than printing a
confident-looking number over two data points.

Also splits arm B by whether a skill fired and by *which* one. A run where no
skill loaded is not a failed measurement of skill content: it is a successful
measurement of the description. A run where the wrong skill loaded is a third
thing again. Collapsing the three hides which of them is broken.
"""
from __future__ import annotations
import argparse, json, pathlib, statistics as st, sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "graders")); sys.path.insert(0, str(ROOT / "tasks"))
import evalstats as es              # noqa: E402
import rubrics                      # noqa: E402
import triggering as tg             # noqa: E402
from tasks import TASKS             # noqa: E402

TOL = es.TIE_TOLERANCE


def load(runs: pathlib.Path, arm: str) -> list[dict]:
    mf = runs / f"manifest_{arm}.jsonl"
    if not mf.exists():
        return []
    text = mf.read_text(encoding="utf-8")
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def fmt(x, nd=2):
    return "—" if x is None else f"{x:.{nd}f}"


def sgn(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}"


def scores_list(xs: list[float]) -> str:
    return ", ".join(f"{x:.2f}" for x in xs) if xs else "—"


def outcome_phrase(kind: str, n_fired: int, n_b: int, delta: float | None) -> str:
    """Name the failure mode, because "no improvement" has three different causes.

    A skill that never loaded and a skill that loaded and did nothing call for
    opposite fixes — rewrite the description, or rewrite the skill — and a reader
    who cannot tell them apart will fix the wrong one.
    """
    if not n_b:
        return "no arm-B runs"
    if delta is None:
        return "no arm-A runs to compare"
    if n_fired == 0:
        return f"discovery failure — no skill ever loaded ({delta:+.2f})"
    partial = "" if n_fired == n_b else f", fired {n_fired}/{n_b}"
    if kind == "control":
        return (f"restrained ({delta:+.2f}){partial}" if delta > -TOL
                else f"over-applied ({delta:+.2f}){partial}")
    if delta >= TOL:
        return f"fired and helped ({delta:+.2f}){partial}"
    if abs(delta) < TOL:
        return f"content failure — fired, no gain ({delta:+.2f}){partial}"
    return f"content failure — fired and regressed ({delta:+.2f}){partial}"


def main() -> int:
    ap = argparse.ArgumentParser(description="write examples/RESULTS.md")
    # Overridable so a synthetic or partial run can be rendered somewhere harmless.
    # RESULTS.md is a published artifact; nothing should be able to half-overwrite
    # it with test data just because a script was run from the wrong directory.
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"),
                    help="where manifest_{a,b}.jsonl and the answer files live")
    ap.add_argument("--out", default=str(ROOT / "RESULTS.md"))
    args = ap.parse_args()
    runs = pathlib.Path(args.runs_dir)

    rows = load(runs, "a") + load(runs, "b")
    if not rows:
        print(f"nothing recorded yet under {runs}", file=sys.stderr); return 1

    by = defaultdict(list)                 # (task, arm) -> [score]
    fired = defaultdict(list)              # task -> [score] where a skill fired
    meta = defaultdict(list)               # arm -> [row]
    b_by_task = defaultdict(list)          # task -> [arm-B row]
    missing = 0
    for r in rows:
        p = runs / r["arm"] / r["file"]
        if not p.exists():
            missing += 1
            continue
        meta[r["arm"]].append(r)
        if r["arm"] == "b":
            b_by_task[r["task"]].append(r)
        # Sessions emit box-drawing and em dashes; the platform default encoding
        # would refuse a perfectly good answer file on Windows.
        answer = p.read_text(encoding="utf-8", errors="replace")
        s = rubrics.grade(r["task"], answer)["score"]
        if s is None:
            continue
        by[(r["task"], r["arm"])].append(s)
        if r["arm"] == "b" and tg.any_fired(r):
            fired[r["task"]].append(s)

    # Paired by task: a task only enters an aggregate if both arms ran it. An
    # unpaired task in a mean delta would compare a task to a different task.
    paired = []
    for t in TASKS:
        a, b = by.get((t["id"], "a"), []), by.get((t["id"], "b"), [])
        if not a or not b:
            continue
        paired.append(dict(id=t["id"], kind=t["kind"], a=a, b=b,
                           ma=st.mean(a), mb=st.mean(b), delta=st.mean(b) - st.mean(a)))
    deltas = [p["delta"] for p in paired]

    out = ["# Results", "",
           "Generated by `examples/report.py`. Per task, never aggregate-only.", ""]

    # ---- headline: the aggregate, with the uncertainty attached to it
    out += ["## Headline", ""]
    n_a, n_b = len(meta.get("a", [])), len(meta.get("b", []))
    if not paired:
        arms = ", ".join(f"arm {k}: {len(v)} runs" for k, v in sorted(meta.items()))
        out += [f"No task has runs in **both** arms yet ({arms or 'nothing recorded'}), so "
                "there is no delta to report and no interval to put around one. The per-task "
                "table below is the whole of what exists.", ""]
    else:
        counts = es.wtl(deltas)
        ci = es.bootstrap_ci_mean(deltas)
        dz = es.cohens_dz(deltas)
        per_task_cliff = [es.cliffs_delta(p["a"], p["b"]) for p in paired]
        per_task_cliff = [c for c in per_task_cliff if c is not None]
        cliff = st.mean(per_task_cliff) if per_task_cliff else None

        ci_line = (f"[{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci else
                   f"not enough paired tasks to bootstrap "
                   f"({len(deltas)} < {es.MIN_BOOTSTRAP_N} needed)")
        block = [
            f"Skill arm wins: {counts['win']}",
            f"Ties:           {counts['tie']}",
            f"Losses:         {counts['loss']}",
            "",
            "Mean score (task-weighted)",
            f"  A      {st.mean([p['ma'] for p in paired]):.2f}",
            f"  B      {st.mean([p['mb'] for p in paired]):.2f}",
            f"  delta  {st.mean(deltas):+.2f}",
            "",
            "Median per-task score",
            f"  A      {st.median([p['ma'] for p in paired]):.2f}",
            f"  B      {st.median([p['mb'] for p in paired]):.2f}",
            f"  delta  {st.median(deltas):+.2f}",
            "",
            f"Bootstrap {es.CI_LEVEL:.0%} CI on the mean delta: {ci_line}",
            f"  {es.BOOTSTRAP_ITERS} resamples of the {len(deltas)} paired tasks, "
            f"random.Random({es.BOOTSTRAP_SEED})",
            "",
            "Effect size",
            f"  Cohen's d_z (paired, across tasks)   {sgn(dz)}"
            + ("" if dz is not None else "  (undefined: needs >= 2 tasks and non-zero spread)"),
            f"  Cliff's delta (within task, meaned)  {sgn(cliff)}"
            f"  ({es.cliff_label(cliff)})",
        ]
        out += ["```", *block, "```", "",
                f"{len(paired)} of {len(TASKS)} tasks have runs in both arms "
                f"({n_a} arm-A runs, {n_b} arm-B runs"
                + (f", {missing} recorded run(s) had no answer file" if missing else "") + "). "
                "Every aggregate here is **task-weighted** — each task contributes its own "
                "per-run mean once — so a task that got five runs cannot outvote one that "
                "got three.", "",
                f"A task counts as a **tie** when |delta| < {TOL:.2f}. A rubric score is the "
                "mean of a handful of binary checks, so one check on the widest rubric moves a "
                "single run by 0.14: any delta from a *consistent* difference between the arms "
                f"clears {TOL:.2f} easily, and anything under it is one check flipping in a "
                "minority of runs.", "",
                "The interval is a **percentile bootstrap resampling tasks, not runs**. Runs of "
                "one task share a prompt and a rubric, so they are not independent draws and "
                "resampling them would narrow the interval by counting the same task twice. "
                "Because the 16 tasks were hand-picked rather than sampled, the interval "
                "describes uncertainty from this task mix and from run noise — not from any "
                "population of \"all coding tasks\". Seed and resample count are fixed in "
                "`evalstats.py` so the published interval is reproducible.", "",
                "Two effect sizes, because neither is sufficient alone. **Cohen's d_z** is the "
                "paired standardised mean difference over per-task deltas, which is the effect "
                "size that matches how the delta was computed; it also assumes a spread that a "
                "dozen clumped 0–1 scores do not really have. **Cliff's delta** is "
                "distribution-free — the chance a random arm-B run beats a random arm-A run on "
                "the same task, minus the reverse — computed within each task so task "
                "difficulty cannot drive it. At this n both are indicative only: with "
                f"{len(deltas)} paired tasks the ranking of tasks is stable long before the "
                "magnitude is, and a d_z above 1 should be read as \"the sign is probably "
                "right\", not as a measured size.", ""]
        if ci and len(deltas) < es.THIN_BOOTSTRAP_N:
            out += [f"**Thin.** {len(deltas)} paired tasks is few enough that the interval is "
                    "itself uncertain; a bootstrap cannot invent information the sample does "
                    "not contain. Treat it as a floor on the uncertainty, not a measurement "
                    "of it.", ""]

    # ---- headline, per task
    out += ["## Per task", "",
            "| task | kind | skill | A mean | A sd | B mean | B sd | delta | verdict | n (A/B) | fired |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    deltas_by_kind = defaultdict(list)
    for t in TASKS:
        tid = t["id"]
        a, b = by.get((tid, "a"), []), by.get((tid, "b"), [])
        if not a and not b:
            continue
        ma = st.mean(a) if a else None
        mb = st.mean(b) if b else None
        sa = st.stdev(a) if len(a) > 1 else (0.0 if a else None)
        sb = st.stdev(b) if len(b) > 1 else (0.0 if b else None)
        d = (mb - ma) if (ma is not None and mb is not None) else None
        if d is not None:
            deltas_by_kind[t["kind"]].append(d)
        nb_fired = len(fired.get(tid, []))
        out.append(f"| {tid} | {t['kind']} | {t['skill']} | {fmt(ma)} | {fmt(sa)} | "
                   f"{fmt(mb)} | {fmt(sb)} | {sgn(d)} | {es.classify(d) or '—'} | "
                   f"{len(a)}/{len(b)} | {nb_fired}/{len(b)} |")

    # ---- the spread behind those means. A mean of three runs is three numbers;
    # printing them costs one column and stops the mean being taken on faith.
    out += ["", "## Per-task spread", "",
            "Every graded run, not only its mean. Two runs at 1.00 and one at 0.00 is a "
            "different finding from three at 0.67, and the mean cannot tell them apart.", "",
            "| task | n (A/B) | A scores | A median | B scores | B median |",
            "|---|---|---|---|---|---|"]
    for t in TASKS:
        a, b = by.get((t["id"], "a"), []), by.get((t["id"], "b"), [])
        if not a and not b:
            continue
        out.append(f"| {t['id']} | {len(a)}/{len(b)} | {scores_list(a)} | "
                   f"{fmt(st.median(a)) if a else '—'} | {scores_list(b)} | "
                   f"{fmt(st.median(b)) if b else '—'} |")

    # ---- by kind. The traps and controls are the interesting rows.
    out += ["", "## By task kind", "",
            "The controls are where skills can *lose*: there the correct behaviour is "
            "not to apply the skill. A negative delta on a control is the most "
            "important number in this file.", "",
            "| kind | tasks | mean delta | median delta | worst task delta | W/T/L |",
            "|---|---|---|---|---|---|"]
    for kind in ("positive", "trap", "control"):
        ds = deltas_by_kind.get(kind, [])
        if not ds:
            continue
        c = es.wtl(ds)
        out.append(f"| {kind} | {len(ds)} | {st.mean(ds):+.2f} | {st.median(ds):+.2f} | "
                   f"{min(ds):+.2f} | {c['win']}/{c['tie']}/{c['loss']} |")

    # ---- triggering
    b_rows = meta.get("b", [])
    n_fired = sum(1 for r in b_rows if tg.any_fired(r))
    labels = tg.counts(b_rows)
    out += ["", "## Triggering", ""]
    if not b_rows:
        out += ["No arm-B runs recorded, so nothing is known about triggering yet.", ""]
    else:
        wrong_runs = sum(1 for r in b_rows
                         if tg.fired_skills(r) and tg.expected_skill(r["task"])
                         not in tg.fired_skills(r))
        out += [f"A skill fired in **{n_fired} of {len(b_rows)}** arm-B runs "
                f"({100*n_fired/len(b_rows):.0f}%). Of those runs: "
                f"{labels[tg.INTENDED]} loaded the intended skill and nothing else, "
                f"{labels[tg.INTENDED_PLUS]} loaded it alongside another, "
                f"{labels[tg.WRONG]} loaded only an unrelated one, "
                f"{labels[tg.NONE]} loaded nothing.", "",
                "A skill that never loads is worth zero in production no matter how good its "
                "content is, and the two failures need opposite fixes — a better description, "
                "or better content. `trigger_benchmark.py` scores discovery on its own, with "
                "precision and recall; this section is the joint view against the scores.", ""]

        # conditional gain, stated in percentage points because that is the claim
        # a reader will quote. Restricted to tasks where both arms ran and a skill
        # fired at least once, so the two numbers describe the same tasks.
        cond = [p for p in paired if fired.get(p["id"])]
        if cond:
            d_all = st.mean([p["delta"] for p in cond])
            d_fired = st.mean([st.mean(fired[p["id"]]) - p["ma"] for p in cond])
            dead = len(paired) - len(cond)
            out += [f"Over the **{len(cond)}** task(s) with runs in both arms where a skill "
                    f"fired at least once: arm B gains **{100*d_fired:+.0f} percentage points** "
                    f"on the runs where a skill actually fired, against "
                    f"**{100*d_all:+.0f} pp** across all of its runs on **those same tasks** — "
                    "the two figures cover one task set on purpose, because comparing a "
                    "conditional mean to a mean over a different set of tasks is not a "
                    f"comparison. Across all {len(paired)} paired task(s)"
                    + (f", including the {dead} where no skill ever fired" if dead else "")
                    + f", the gain is **{100*st.mean(deltas):+.0f} pp**, and a skill fired in "
                    f"**{100*n_fired/len(b_rows):.0f}%** of arm-B runs.", "",
                    "The conditional figure is the ceiling the descriptions are currently "
                    "throwing away. It is not the number to quote as the skill's effect: "
                    "conditioning on firing also conditions on the agent having recognised the "
                    "task, and those are the runs where it was most likely to do well anyway.",
                    ""]
        elif n_fired == 0:
            out += ["**No skill ever fired.** Every arm-B run measures the descriptions, not "
                    "the content, and a null result here is a finding about triggering. Do not "
                    "report it as a finding about the skills.", ""]

        out += ["| task | expected skill | triggered skill(s) | trigger correct? | outcome |",
                "|---|---|---|---|---|"]
        for t in TASKS:
            tid = t["id"]
            brs = b_by_task.get(tid, [])
            if not brs:
                continue
            seen: dict[str, int] = {}
            ok = 0
            for r in brs:
                for s in tg.fired_skills(r) or ["none"]:
                    seen[s] = seen.get(s, 0) + 1
                v = tg.verdict(tid, tg.classify_run(r))
                ok += 1 if v.startswith(("yes", "allowed")) else 0
            trig = ", ".join(f"{k} ({v}/{len(brs)})" for k, v in
                             sorted(seen.items(), key=lambda kv: -kv[1]))
            a, b = by.get((tid, "a"), []), by.get((tid, "b"), [])
            d = (st.mean(b) - st.mean(a)) if (a and b) else None
            nf = sum(1 for r in brs if tg.any_fired(r))
            out.append(f"| {tid} | {t['skill']}"
                       + ("" if tg.trigger_required(tid) else " *(control: none wanted)*")
                       + f" | {trig} | {ok}/{len(brs)} | "
                       + outcome_phrase(t["kind"], nf, len(b), d) + " |")

        if any(fired.get(t["id"]) and len(fired[t["id"]]) != len(by.get((t["id"], "b"), []))
               for t in TASKS):
            out += ["", "Where a skill fired in some runs of a task but not others, the two "
                    "arm-B means split:", "",
                    "| task | B mean (all) | B mean (fired only) | n fired |", "|---|---|---|---|"]
            for t in TASKS:
                tid, f = t["id"], fired.get(t["id"], [])
                b = by.get((tid, "b"), [])
                if b and f and len(f) != len(b):
                    out.append(f"| {tid} | {st.mean(b):.2f} | {st.mean(f):.2f} | {len(f)}/{len(b)} |")

    # ---- effort confound
    out += ["", "## Effort check", "",
            "If arm B simply did more work, the gain may not be the skill.", "",
            "| arm | runs | mean turns | mean tools/run | mean cost usd |", "|---|---|---|---|---|"]
    for arm in ("a", "b"):
        rs = meta.get(arm, [])
        if not rs:
            continue
        turns = [r["turns"] for r in rs if r.get("turns") is not None]
        tools = [len(r.get("tools_used") or []) for r in rs]
        cost = [r["cost_usd"] for r in rs if r.get("cost_usd") is not None]
        out.append(f"| {arm} | {len(rs)} | {fmt(st.mean(turns),1) if turns else '—'} | "
                   f"{fmt(st.mean(tools),1) if tools else '—'} | "
                   f"{fmt(st.mean(cost),3) if cost else '—'} |")

    out += ["", "## Threats to validity", "",
            "- Both arms run inside a Claude Code session, which carries a large constant "
            "system prompt and a tool loop. That is held constant, but it widens variance "
            "relative to a single-turn API call.",
            "- n is small. Treat per-task deltas smaller than the reported sd as noise.",
            "- The bootstrap interval assumes the paired tasks are exchangeable. They are not "
            "a random sample of anything — they were written to probe specific failure modes, "
            "including three controls chosen to make the skills lose. The interval bounds "
            "sampling noise within this task set and nothing wider.",
            f"- Effect sizes at {len(deltas)} paired task(s) are indicative. d_z in particular "
            "is unstable when the per-task deltas are few and coarse; a large value can come "
            "from small spread rather than a large effect.",
            f"- The win/tie/loss split depends on the {TOL:.2f} tie tolerance documented above. "
            "A different tolerance moves tasks between the columns; the per-task table is the "
            "record, not the counts.",
            "- Triggering is detected from the transcript (a `Skill` call or a read of a "
            "`SKILL.md`), so a session that absorbed a description without loading the file "
            "counts as not fired. That biases the fire rate down, not up.",
            "- Arm B is the only arm with skills installed; nothing else differs. "
            "`check_contamination.py` verifies arm A never read one.",
            "- Grader rubrics were pre-registered and are validated against fixtures "
            "(`validate_graders.py`), but they are still proxies for code quality.", ""]

    dest = pathlib.Path(args.out)
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {dest}")
    print("\n".join(out[:40]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
