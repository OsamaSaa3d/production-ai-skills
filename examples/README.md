# Does any of this actually help? — a measured A/B

> **Status: harness built and validated. Not yet run.** No generation has happened,
> so there are no results below to read. Everything here — tasks, graders, rubrics —
> was committed *before* any output existed. That is the point.

A hand-picked before/after transcript proves nothing and everyone knows it. This is
built so a skeptic can run it and get our numbers.

## Method

Two arms, both **Claude Code sessions**, same model, same tools, same permissions.
Two empty scratch directories created by `setup_arms.py`:

- **Arm A** — an empty directory. Gets the task, nothing else.
- **Arm B** — an empty directory with all **ten** skills installed under `.claude/skills/`.

Arm A is not a strawman: it is the same agent doing the same task, and the only
difference between the arms is whether the skills are on disk.

Arm B gets all ten skills, not the relevant one. The agent picks from ten
descriptions exactly as a real user's would, which makes **triggering part of what
is measured** rather than something we hand it for free. Runs where no skill fired
are reported separately — such a run measures the *description*, not the content.

Testing through Claude Code rather than raw API calls is deliberate. It is the
condition the skills actually ship into, and it is the only way to exercise the two
mechanisms that matter most: description-based triggering, and progressive
disclosure of the 58 reference files. Pasting a `SKILL.md` into a system prompt
would test neither.

`n` is fixed before running. Prefer n=5 on the traps and controls, where the effects
should be largest.

## The task set

16 tasks, none naming a technique — phrased the way a user would phrase them, per
`tool-design/references/eval-loop.md`, which is explicit that a task naming the tool
call measures nothing.

| Kind | Count | Correct behaviour |
|---|---|---|
| positive | 10 | Apply the skill |
| trap | 3 | The tempting answer is wrong (prompt-described query grammar; two "agents" that are really workflows) |
| control | 3 | **Do not** apply the skill — a load-bearing framework, prose output, a trivial tool |

The controls are the part most demos omit, and the reason to trust this one.
Over-application is the most plausible way these skills are actually bad: a skill
that makes the model bolt strict mode onto a prose summary, or rip out a framework
the user depends on, is a net negative. Every skill here has a "when to break the
rules" section; the controls test whether the model still breaks them correctly.

Tasks `t15` and `t16` do the mirror job — they check the skill does not over-correct
into always answering "use a workflow" when an agent or a parallel decomposition is
genuinely right.

## Metrics

**Tier 1 — deterministic, ~80% of the signal.** 51 checks across 16 rubrics, AST over
the generated code plus regex over prose. No judge, no API call, no opinion. Examples:

- `strict: true` present; `additionalProperties: false` on every object
- no `langchain` / `instructor` / `AgentExecutor` import — *except* on the control, where keeping it is the pass
- tool errors caught and returned as data rather than raised
- **`sql_is_safe`** — the model must not be the source of executed SQL
- `model_driven_loop` — AST-detected, and **inverted** on the two architecture traps, where the pass condition is the *absence* of a loop

Every check cites the line of the skill it tests. A check that cannot cite one does
not belong in the rubric — that rule is what stops a grader being written to flatter
the result.

**Tier 2 — calibrated judge**, for the genuinely subjective residue only (justification
quality, scope discipline). One dimension per criterion. Calibrate against 30 hand
labels and require ≥80% agreement before it gates anything. Not judged by the model
under test: self-preference would bias exactly the comparison being made.

**Tier 3 — effort and cost.** Skills add context, and an agent that loads one may also
take more turns. `report.py` prints mean turns, tool calls and cost per arm, because if
arm B simply did more work, the gain may not be the skill.

## Reporting uncertainty

A mean delta over three runs is a number, not evidence. `report.py` therefore reports
the spread alongside every aggregate, and `evalstats.py` holds the arithmetic — stdlib
only, no numpy, so there is nothing to install:

- **Mean and median**, per arm and per task, plus **every individual run score**. Two
  runs at 1.00 and one at 0.00 is a different finding from three at 0.67.
- **Win / tie / loss by task.** A task is a tie when |delta| < 0.05. That tolerance is
  not arbitrary: a rubric score is the mean of a handful of binary checks, so one check
  on the widest rubric (7 checks) moves a run by 0.14. Any delta from a consistent
  difference between the arms clears 0.05; anything under it is one check flipping in a
  minority of runs.
- **A bootstrap 95% CI on the mean delta**, 10,000 resamples with a fixed seed so the
  published interval is reproducible to the last digit. It resamples **tasks, not runs**:
  runs of one task share a prompt and a rubric and are not independent draws.
- **Two effect sizes.** Cohen's d_z, the paired standardised mean difference across
  per-task deltas, which matches how the delta was computed; and Cliff's delta, which is
  distribution-free and so does not pretend a dozen clumped 0–1 scores are normal. At
  this n both are indicative of sign, not of size, and the report says so.

Every one of these is guarded against degenerate n. Below three paired tasks the report
prints *"not enough paired tasks to bootstrap"* rather than a zero-width interval, d_z
reports undefined rather than dividing by a zero standard deviation, and a run with only
one arm recorded produces a report that says there is no delta to report. The first real
run will be n=1; a reporting script that fakes a confidence interval on it would be worse
than no report.

## The five commitments

1. **Graders are pre-registered.** `graders/` was committed before any generation existed; git history proves it.
2. **Grading is blind.** Filenames are salted hashes; the rubric never receives the arm.
3. **No task reuses a skill's own example.** Otherwise it measures recall, not transfer.
4. **Every generation is published**, including the ugly ones.
5. **Losses stay in the headline table.** `naming-experiments.md` argues null results are the valuable half; a clean sweep reads as fabricated.

## Grader validation

A grader nobody tested is a number nobody should trust. Each rubric was validated
against hand-written naive/skilled fixture pairs in `fixtures/` before any run:

**All 16 rubrics are validated**, and `examples/validate_graders.py` enforces it in
CI: every rubric must separate its pair by at least 0.40 or the build fails.

| | Worse fixture | Better fixture | Separation |
|---|---|---|---|
| 10 positives | 0.00–0.50 | 1.00 | +0.50 to +1.00 |
| 3 traps (`t09`, `t13`, `t14`) | 0.00 | 1.00 | +1.00 |
| 3 controls (`t04`, `t08`, `t12`) | 0.00–0.50 *(over-applied)* | 1.00 *(restrained)* | +0.50 to +1.00 |

The control rows are the important ones: there, the **restrained** answer scores high
and the skill-applying answer scores low. The grader can and will penalise the skills
arm. That is what makes the outcome falsifiable rather than decorative.

Writing these fixtures found **six real bugs in the graders**, all before a cent was
spent — among them a false positive on `sql_is_safe` (the most consequential check,
which was failing a correctly parameterised query), a `uses_native_tool_calling` that
was fooled by `AgentExecutor(tools=...)`, a `keeps_framework` that passed an answer
for *mentioning* LangGraph while removing it, and an `additionalProperties` check that
penalised the idiomatic Pydantic path the skill itself recommends.

Run it yourself — no API key needed:

```bash
python3 examples/validate_graders.py
```

## Running it

No API key and no separate spend: the generations come from Claude Code sessions.
`examples/PROMPT.md` is the full brief for an orchestrating session.

```bash
python3 examples/setup_arms.py --force      # two clean scratch dirs, skills in B only
# ... drive one Claude Code session per task per arm, in its arm directory ...
python3 examples/record.py --arm b --task t09 --run 0 --answer-file out.md \
        --skill-triggered tool-design --turns 4
python3 examples/check_contamination.py     # arm A must never have seen a skill
python3 examples/grade.py                   # blind, writes results.tsv
python3 examples/report.py                  # writes RESULTS.md
python3 examples/trigger_benchmark.py       # writes TRIGGERING.md
```

`report.py` and `trigger_benchmark.py` both take `--runs-dir` and `--out`. The defaults
are the real manifests and the published paths; the flags exist so a synthetic or partial
run can be rendered somewhere harmless, which is what `validate_report.py` does:

```bash
python3 examples/validate_report.py   # no key, no API calls, writes nothing outside /tmp
```

It builds fake manifests from the `fixtures/` answers and asserts both scripts behave at
n=0, n=1 and n=3, when no skill ever fired, when the wrong skill fired, when several
fired at once, and when only one arm has runs. Those are the cases real data will not
exercise until it is too late to find out.

### The control that everything rests on

Both arms run in empty scratch directories with **no path to this repository**. If a
session can reach the repo, arm A can read the skills and the comparison is worthless
— and it need not be deliberate: an agent asked to write tool-calling code, sitting in
a repo full of tool-calling guidance, will plausibly read it.

`check_contamination.py` scans every arm-A answer and transcript for skill directory
names and distinctive skill phrasing, and exits non-zero if it finds any. Discard and
re-run anything it flags.

## Triggering

Measured natively: arm B has all ten skills and picks for itself, so every run records
which skills fired. This matters because a perfect skill whose description never matches
is worth zero in production, and a design that hands the agent the right skill would hide
that entirely.

A skill can fail in two unrelated ways and they need opposite fixes:

- **discovery failure** — the skill never loaded. That measures the *description*.
- **content failure** — the skill loaded and the score did not improve. That measures the
  *skill*.

`RESULTS.md` separates them. It reports the fire rate overall and per task, splits arm B
into all-runs and fired-only means, and carries a per-task table of `expected skill /
triggered skill(s) / trigger correct? / outcome` where the outcome column names the
failure mode rather than leaving a reader to infer it. The conditional gain is stated in
percentage points, both over the tasks where a skill fired at least once and over every
paired task, so the two figures cover the same tasks and can be compared honestly. A
conditional gain is a ceiling, not an effect: conditioning on firing also conditions on
the agent having recognised the task.

`trigger_benchmark.py` scores discovery **on its own**. It reads only the arm-B manifest
— never an answer, never a rubric — and reports precision, recall, F1, no-trigger rate
and wrong-trigger rate over the same 16 tasks, writing `TRIGGERING.md`. The unit is one
run, treated as one retrieval attempt against the ten installed skills: a true positive
is a run where the intended skill fired, a false positive is each load that was not the
intended skill, a false negative is a run where it did not fire. Precision therefore
divides by skill *loads* and recall by *runs*; the definitions are in the script's
docstring and reprinted in its output, because a precision figure whose denominator a
reader has to reverse-engineer is not a result.

The **three controls are excluded from precision and recall**, and reported separately.
There the correct behaviour is not to apply the skill, so firing nothing is a pass; and
because every skill carries a "when to break the rules" section, loading the matching
skill and then staying restrained is defensible too. Only an unrelated skill firing on a
control is a failure. Counting a control's silence as a missed trigger would score the
descriptions as broken for behaving exactly as designed.

**Schema.** `record.py` writes triggering twice: `skill_triggered`, one string or null,
and `skills_triggered`, the full list. Arm B has all ten skills installed, so two firing
at once is a real outcome and a single string would report the first as though it were
the whole story. Rows written before the list existed still have to read back, so both
fields are kept and `triggering.fired_skills` accepts either shape — every reader goes
through it. Detection is transcript-based (a `Skill` call, or a read of a `SKILL.md`), so
a session that absorbed a description without loading the file counts as not fired. That
biases the fire rate down, not up.

## Layout

```
examples/
├── tasks/tasks.py        # the 16 prompts
├── graders/checks.py     # 22 mechanical checks
├── graders/rubrics.py    # 51 per-task checks, each citing a skill line
├── fixtures/             # 32 naive/skilled pairs proving the graders discriminate
├── validate_graders.py   # offline, no key — CI fails if a rubric stops separating
├── validate_report.py    # offline — the reporting layer, against synthetic manifests
├── setup_arms.py         # two clean scratch dirs; skills installed in B only
├── run_arm.py            # drives one arm through fresh headless sessions
├── record.py             # append one generation to the manifest, schema enforced
├── check_contamination.py# arm A must never have seen a skill
├── grade.py              # blind grader -> results.tsv
├── evalstats.py          # bootstrap CI, effect size, win/tie/loss — stdlib only
├── triggering.py         # one reader for "which skills fired", and what should have
├── report.py             # -> RESULTS.md
├── trigger_benchmark.py  # -> TRIGGERING.md, discovery scored on its own
└── PROMPT.md             # the brief for an orchestrating Claude Code session
```

`RESULTS.md` and `TRIGGERING.md` are generated, and are not in this repository yet
because nothing has been run. They are deliberately **not** gitignored: when there are
real numbers, the write-up is the deliverable.
