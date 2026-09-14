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
take more turns. `report.py` prints mean turns and tool calls per arm, because if arm B
simply did more work, the gain may not be the skill.

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
```

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
whether a skill fired and which one. `report.py` reports the fire rate and splits arm B
into all-runs and fired-only means.

This matters because a perfect skill whose description never matches is worth zero in
production, and a design that hands the agent the right skill would hide that entirely.

## Layout

```
examples/
├── tasks/tasks.py        # the 16 prompts
├── graders/checks.py     # 25 mechanical checks
├── graders/rubrics.py    # 51 per-task checks, each citing a skill line
├── fixtures/             # 32 naive/skilled pairs proving the graders discriminate
├── validate_graders.py   # offline, no key — CI fails if a rubric stops separating
├── setup_arms.py         # two clean scratch dirs; skills installed in B only
├── record.py             # append one generation to the manifest, schema enforced
├── check_contamination.py# arm A must never have seen a skill
├── grade.py              # blind grader -> results.tsv
├── report.py             # -> RESULTS.md
└── PROMPT.md             # the brief for an orchestrating Claude Code session
```
