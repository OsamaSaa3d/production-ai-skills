# Brief: run the skills A/B

You are the orchestrating session. You will drive two sets of Claude Code
sub-sessions, grade their output, and write the report. You are not one of the
arms — never answer a task prompt yourself.

**Repo:** this one. Work on `main`. Everything you need is under `examples/`.

Read `examples/README.md` first. It documents the method and the anti-rigging
commitments. Do not weaken any of them.

---

## Step 0 — verify the harness before generating anything

```bash
python3 scripts/lint_skills.py          # must exit 0
python3 examples/validate_graders.py    # must exit 0 — all 16 rubrics separate
```

If either fails, stop and fix it. Generating against a broken grader wastes the runs.

## Step 1 — create the two arms

```bash
python3 examples/setup_arms.py --force
```

This creates two **empty** scratch directories:

- `/tmp/skills-eval/arm-a` — nothing in it
- `/tmp/skills-eval/arm-b` — all ten skills under `.claude/skills/`

**This isolation is the control the entire experiment rests on.** Every session must
run with its arm directory as the working directory, and must have no path back to
this repository — no `--add-dir`, no absolute paths into the repo, nothing. If an
arm-A session can read a `SKILL.md`, it is not a control.

Confirm both directories look right before continuing.

## Step 2 — run the tasks

The 16 tasks are in `examples/tasks/tasks.py`. For each task, in **both** arms,
**n=3** (use n=5 on the traps `t09`, `t13`, `t14` and the controls `t04`, `t08`,
`t12` if you have the budget — that is where the effects should be largest).

For every run:

- Start a **fresh** session in the arm's directory. Never reuse a session across
  tasks or runs; carryover contaminates later ones.
- Give it the task's `prompt` field **verbatim**. Do not add hints, do not mention
  skills, do not rephrase.
- Use the same model for both arms. sonnet-5 with high effort.
- Capture the full final answer and, if you can, the transcript.

A headless invocation is the easiest way to script this, e.g. from inside the arm
directory:

```bash
cd /tmp/skills-eval/arm-a && claude -p "<task prompt>" > /tmp/out.md
```

Use whatever invocation actually works in your environment; the requirement is the
working directory and the verbatim prompt, not a specific flag.

Then record it:

```bash
python3 examples/record.py \
  --arm b --task t09 --run 0 \
  --answer-file /tmp/out.md \
  --model <model-id> \
  --turns <n> --tools-used "Read,Write" \
  --skill-triggered tool-design \
  --transcript-file /tmp/transcript.txt
```

`--skill-triggered` is the name of the skill the session actually loaded, or omitted
if none fired. **Getting this right matters** — it is the triggering metric, and a run
where no skill fired measures the description rather than the content.

Filenames are salted hashes so grading stays blind. Do not rename them.

## Step 3 — verify the control held

```bash
python3 examples/check_contamination.py
```

It scans every arm-A answer and transcript for skill directory names and distinctive
skill phrasing. **If it flags a run, discard that run and redo it** in a clean
directory. Do not rationalise a flagged run into the results.

It also reports the arm-B fire rate. If no skill ever fired, say so prominently — a
null result then is a finding about the descriptions, not the content.

## Step 4 — grade and report

```bash
python3 examples/grade.py     # blind; writes results.tsv
python3 examples/report.py    # writes RESULTS.md
```

Then read the failures. **Do not tune a grader to improve a score.** If a check is
genuinely wrong — a false positive on a correct answer — fix the check, note the fix
in `RESULTS.md`, and re-grade **both** arms. Never apply a fix that only helps one arm.
Six such bugs were already found and fixed during construction; more are possible.

## Step 5 — write up

`report.py` produces the tables. Expand `examples/RESULTS.md` into something a
stranger can act on:

1. **Per-task table** — already generated. Never replace it with an aggregate.
2. **By kind** — positives, traps, controls, separately. A negative delta on a control
   is the most important number in the file and belongs near the top, not buried.
3. **Triggering** — fire rate, and arm-B means conditional on the skill firing.
4. **Effort** — mean turns and tool calls per arm, so a reader can judge whether arm B
   just did more work.
5. **Threats to validity** — written honestly. Small n, session variance, any grader
   fix you made, any task where the result is ambiguous.
6. **A plain verdict** — where the skills help, where they do not, which to install first.

Charts are welcome if they clarify; put them in `examples/figures/`.

## Step 6 — update the repo

- Update the top-level `README.md` with what the data now supports. Add a short results
  section linking to `examples/RESULTS.md`. Correct anything the results contradict.
  **If the numbers are unflattering, say so plainly** — the repo's credibility rests on
  not overclaiming.
- Read the repo once more with fresh eyes and fix anything stale, inconsistent, or
  confusing to a first-time reader.
- `python3 scripts/lint_skills.py` and `python3 examples/validate_graders.py` must both
  exit 0.
- Commit the raw outputs too. `examples/.gitignore` currently excludes `runs/` and
  `results.tsv` — remove those lines, because for this eval the raw generations are the
  deliverable.
- Commit and push to `main` in logical commits.

## Rules

- **Never edit a `SKILL.md` to improve a score.** That is tuning the thing being
  measured. If the eval exposes a real defect in a skill, note it in `RESULTS.md` and
  fix it in a **separate commit after** the results are committed, so the before/after
  stays honest.
- Publish every generation, including the bad ones.
- If arm B loses somewhere, it stays in the headline table.
- Report what you actually ran. If a step failed, or you ran fewer than n anywhere,
  say so in `RESULTS.md`.
