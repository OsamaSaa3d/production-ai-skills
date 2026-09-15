#!/usr/bin/env python3
"""Exercise report.py and trigger_benchmark.py against synthetic manifests.

The reporting layer is the part of this harness that will be read by people who
did not run it, and it is the part that cannot be checked by running it once on
real data: the interesting cases are the degenerate ones. n=1, a single arm with
runs, a task set where nothing ever triggered, a run where the wrong skill fired,
a run where three fired at once. Every one of those is a plausible first result,
and a reporting script that crashes or quietly prints a zero-width confidence
interval on one of them is worse than no report.

So this builds fake manifests in a temporary directory, points both scripts at
them with `--runs-dir` and `--out`, and asserts they exit clean and say the right
thing. Answer contents are the real `fixtures/` pairs — naive for arm A, skilled
for arm B, over-applied for arm B on the two controls that have one — so the
rubrics return realistic scores rather than 0.00 and 1.00 everywhere.

Nothing here writes to examples/runs/ or to RESULTS.md. The numbers it produces
are fabricated and must never be published; that is the whole reason both
scripts take an explicit output path.

  python3 examples/validate_report.py            # CI: assertions only
  python3 examples/validate_report.py --show      # also dump the generated markdown
"""
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "graders")); sys.path.insert(0, str(ROOT / "tasks"))
import evalstats as es              # noqa: E402
import triggering as tg             # noqa: E402
from tasks import BY_ID, TASKS      # noqa: E402

FIXTURES = ROOT / "fixtures"
# Arm B on a control has no "skilled" fixture: the pair there is naive (restrained,
# correct) vs over-applied (the skill misfiring). Handing arm B the over-applied one
# is the honest synthetic worst case — it makes arm B lose the controls, which is
# exactly the shape of result the report has to be able to render.
ARM_B_OVERRIDE = {"t08": "overapplied", "t12": "overapplied"}
OTHER_SKILL = "context-and-memory"      # installed in arm B, intended by no task


def answer_for(tid: str, arm: str, fired: list[str]) -> str:
    """Arm B gets the skilled fixture only when a skill actually fired.

    Otherwise the synthetic data would give every arm-B run the same score whether
    or not it loaded anything, and the fired-only conditional means — the numbers
    that separate a discovery failure from a content failure — would be identical
    to the unconditional ones by construction, testing nothing.
    """
    if arm == "a" or not fired:
        sfx = "naive"
    else:
        sfx = ARM_B_OVERRIDE.get(tid, "skilled")
    return (FIXTURES / f"{tid}_{sfx}.md").read_text(encoding="utf-8")


def make_row(tid: str, arm: str, run: int, fired: list[str], *, legacy: bool = False) -> dict:
    row = dict(file=f"{tid}-{arm}-r{run}.md", task=tid, arm=arm, run=run,
               model="synthetic", turns=4 + run, input_tokens=1000, output_tokens=200,
               cost_usd=0.10 + 0.01 * run, tools_used=["Read", "Write"], ts=0.0)
    if legacy:                       # the shape record.py wrote before the list existed
        row["skill_triggered"] = fired[0] if fired else None
    else:
        row["skill_triggered"] = fired[0] if fired else None
        row["skills_triggered"] = fired
    return row


def build(tmp: pathlib.Path, *, runs: int, fire, tasks=None, arms=("a", "b"),
          legacy: bool = False) -> pathlib.Path:
    """Write one synthetic runs/ tree. `fire(task) -> [skill]` decides triggering."""
    d = tmp / "runs"
    for arm in arms:
        (d / arm).mkdir(parents=True, exist_ok=True)
        rows = []
        for t in (tasks or TASKS):
            for k in range(runs):
                fired = fire(t, k) if arm == "b" else []
                r = make_row(t["id"], arm, k, fired, legacy=legacy)
                (d / arm / r["file"]).write_text(answer_for(t["id"], arm, fired),
                                                 encoding="utf-8")
                rows.append(r)
        (d / f"manifest_{arm}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return d


def run(script: str, runs_dir: pathlib.Path, out: pathlib.Path) -> tuple[int, str, str]:
    p = subprocess.run([sys.executable, str(ROOT / script),
                        "--runs-dir", str(runs_dir), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout or "", p.stderr or ""


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def ok(self, cond: bool, msg: str) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'} {msg}")
        if not cond:
            self.failures.append(msg)

    def has(self, text: str, needle: str, msg: str) -> None:
        self.ok(needle in text, msg)


def unit_checks(c: Checker) -> None:
    print("\n[unit] evalstats guards")
    c.ok(es.bootstrap_ci_mean([]) is None, "n=0 deltas -> no interval")
    c.ok(es.bootstrap_ci_mean([0.2]) is None, "n=1 delta -> no interval, not [0.2, 0.2]")
    c.ok(es.bootstrap_ci_mean([0.2, 0.3]) is None,
         f"n=2 deltas -> no interval (MIN_BOOTSTRAP_N={es.MIN_BOOTSTRAP_N})")
    lo, hi = es.bootstrap_ci_mean([0.1, 0.2, 0.3, 0.0, 0.4])
    c.ok(lo < 0.2 < hi, "n=5 deltas -> interval brackets the mean")
    c.ok(es.bootstrap_ci_mean([0.1, 0.2, 0.3]) == es.bootstrap_ci_mean([0.1, 0.2, 0.3]),
         "fixed seed -> identical interval on re-run")
    c.ok(es.cohens_dz([0.2]) is None, "d_z undefined at n=1")
    c.ok(es.cohens_dz([0.2, 0.2, 0.2]) is None, "d_z undefined at zero spread")
    c.ok(es.cohens_dz([0.1, 0.2, 0.3]) is not None, "d_z defined with spread")
    c.ok(es.cliffs_delta([], [1.0]) is None, "Cliff's delta undefined with an empty arm")
    c.ok(es.cliffs_delta([0.0, 0.0], [1.0, 1.0]) == 1.0, "Cliff's delta = 1.0 when B dominates")
    c.ok(es.classify(0.0) == "tie" and es.classify(es.TIE_TOLERANCE / 2) == "tie",
         f"|delta| < {es.TIE_TOLERANCE} is a tie")
    c.ok(es.classify(0.5) == "win" and es.classify(-0.5) == "loss", "sign drives win/loss")

    print("\n[unit] triggering reads both manifest shapes")
    c.ok(tg.fired_skills({"skill_triggered": "tool-design"}) == ["tool-design"],
         "legacy single string")
    c.ok(tg.fired_skills({"skill_triggered": None}) == [], "legacy null")
    c.ok(tg.fired_skills({"skill_triggered": "a", "skills_triggered": ["a", "b"]}) == ["a", "b"],
         "list wins when both fields are present")
    c.ok(tg.fired_skills({"skills_triggered": []}) == [], "empty list")
    c.ok(tg.fired_skills({}) == [], "neither field")
    c.ok(tg.fired_skills({"skills_triggered": ["a", "a"]}) == ["a"], "duplicates collapsed")
    c.ok(tg.classify_run({"task": "t01", "skills_triggered": ["llm-tool-calling"]}) == tg.INTENDED,
         "intended only")
    c.ok(tg.classify_run({"task": "t01", "skills_triggered":
                          ["llm-tool-calling", OTHER_SKILL]}) == tg.INTENDED_PLUS,
         "intended plus another")
    c.ok(tg.classify_run({"task": "t01", "skills_triggered": [OTHER_SKILL]}) == tg.WRONG,
         "wrong only")
    c.ok(tg.classify_run({"task": "t01", "skills_triggered": []}) == tg.NONE, "nothing fired")
    c.ok(tg.trigger_required("t13") and not tg.trigger_required("t12"),
         "traps require a trigger, controls do not")
    c.ok(tg.verdict("t12", tg.NONE).startswith("yes"),
         "a control firing nothing is a pass, not a miss")


def scenarios(c: Checker, show: bool) -> None:
    always = lambda t, k: [t["skill"]]
    never = lambda t, k: []
    wrong = lambda t, k: [OTHER_SKILL]
    multi = lambda t, k: [t["skill"], OTHER_SKILL]

    def mixed(t, k):
        """Realistic: mostly right, sometimes silent, occasionally wrong or doubled."""
        if t["kind"] == "control":
            return [] if k % 2 == 0 else [t["skill"]]
        if t["id"] in ("t06", "t11") and k == 0:
            return []                                   # discovery failure
        if t["id"] == "t15":
            return []                                   # never discovered at all
        if t["id"] == "t10" and k == 1:
            return [OTHER_SKILL]                        # wrong skill
        if t["id"] == "t02":
            return [t["skill"], OTHER_SKILL]            # two fired
        return [t["skill"]]

    cases = [
        ("n=1, intended skill always fires", dict(runs=1, fire=always), None),
        ("n=3, mixed triggering (the realistic case)", dict(runs=3, fire=mixed), "SHOW"),
        ("n=3, no skill ever fired", dict(runs=3, fire=never), None),
        ("n=3, only the wrong skill fired", dict(runs=3, fire=wrong), None),
        ("n=3, two skills fired every run", dict(runs=3, fire=multi), None),
        ("n=3, legacy single-string schema", dict(runs=3, fire=always, legacy=True), None),
        ("2 tasks only — too few pairs to bootstrap",
         dict(runs=3, fire=always, tasks=[BY_ID["t01"], BY_ID["t09"]]), None),
        ("arm A only — no pairs at all", dict(runs=3, fire=always, arms=("a",)), None),
    ]

    for label, kw, mark in cases:
        print(f"\n[scenario] {label}")
        with tempfile.TemporaryDirectory(prefix="skills-eval-selftest-") as td:
            tmp = pathlib.Path(td)
            runs_dir = build(tmp, **kw)
            res, trg = tmp / "RESULTS.md", tmp / "TRIGGERING.md"

            rc, so, se = run("report.py", runs_dir, res)
            c.ok(rc == 0, f"report.py exit 0 (stderr: {se.strip()[:120]})")
            text = res.read_text(encoding="utf-8") if res.exists() else ""
            c.ok(bool(text), "report.py wrote a file")
            for section in ("## Headline", "## Per task", "## Per-task spread",
                            "## By task kind", "## Triggering", "## Effort check",
                            "## Threats to validity"):
                c.has(text, section, f"RESULTS.md has {section}")
            c.ok("nan" not in text.lower(), "no NaN leaked into RESULTS.md")

            n_pairs = 0 if kw.get("arms") == ("a",) else len(kw.get("tasks") or TASKS)
            if n_pairs == 0:
                c.has(text, "No task has runs in **both** arms", "states there is no delta")
            elif n_pairs < es.MIN_BOOTSTRAP_N:
                c.has(text, "not enough paired tasks to bootstrap", "refuses to fake an interval")
            else:
                c.has(text, "Bootstrap 95% CI on the mean delta: [", "reports an interval")
                c.has(text, f"random.Random({es.BOOTSTRAP_SEED})", "names the seed")
                c.has(text, f"{es.BOOTSTRAP_ITERS} resamples", "names the resample count")
                c.has(text, "Cohen's d_z", "names the effect size")
                c.has(text, "Skill arm wins:", "reports win/tie/loss")

            rc, so, se = run("trigger_benchmark.py", runs_dir, trg)
            if kw.get("arms") == ("a",):
                c.ok(rc == 1, "trigger_benchmark.py exits 1 with no arm-B runs")
                c.has(se, "no arm-B runs recorded", "says why it could not score")
            else:
                c.ok(rc == 0, f"trigger_benchmark.py exit 0 (stderr: {se.strip()[:120]})")
                ttext = trg.read_text(encoding="utf-8") if trg.exists() else ""
                for section in ("## Definitions", "## Headline", "## Per task", "## Controls"):
                    c.has(ttext, section, f"TRIGGERING.md has {section}")
                c.has(ttext, "precision", "defines precision")
                c.has(ttext, "recall", "defines recall")
                c.has(so, "F1=", "prints an F1 to stdout")
                c.ok("nan" not in ttext.lower(), "no NaN leaked into TRIGGERING.md")
                if kw["fire"] is never:
                    c.has(ttext, "intended skill never fired", "flags total discovery failure")
                    c.has(so, "no-trigger=100%", "no-trigger rate is 100%")
                if kw["fire"] is wrong:
                    c.has(so, "wrong-trigger=100%", "wrong-trigger rate is 100%")
                    c.has(so, "precision=0.00", "precision is 0 when only the wrong skill fires")
                if kw["fire"] is multi:
                    c.has(so, "multi-fire=100%", "multi-fire rate is 100%")
                    c.has(so, "recall=1.00", "recall stays 1.0 when the intended skill also fired")

            if show and mark == "SHOW":
                print("\n" + "=" * 78)
                print("SYNTHETIC RESULTS.md\n" + "=" * 78 + "\n" + text)
                print("\n" + "=" * 78)
                print("SYNTHETIC TRIGGERING.md\n" + "=" * 78 + "\n"
                      + trg.read_text(encoding="utf-8"))

    # Nothing recorded at all: both scripts must decline, not traceback.
    print("\n[scenario] empty runs directory")
    with tempfile.TemporaryDirectory(prefix="skills-eval-selftest-") as td:
        tmp = pathlib.Path(td)
        (tmp / "runs").mkdir()
        rc, so, se = run("report.py", tmp / "runs", tmp / "RESULTS.md")
        c.ok(rc == 1 and "nothing recorded" in se, "report.py declines an empty runs dir")
        c.ok(not (tmp / "RESULTS.md").exists(), "report.py wrote no file when it declined")
        rc, so, se = run("trigger_benchmark.py", tmp / "runs", tmp / "TRIGGERING.md")
        c.ok(rc == 1, "trigger_benchmark.py declines an empty runs dir")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--show", action="store_true",
                    help="print the markdown generated for the realistic scenario")
    args = ap.parse_args()

    c = Checker()
    unit_checks(c)
    scenarios(c, args.show)

    print()
    if c.failures:
        for f in c.failures:
            print(f"FAIL {f}")
        return 1
    print("reporting layer ok on synthetic manifests (n=0, n=1, n=3, no-fire, "
          "wrong-fire, multi-fire, legacy schema)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
