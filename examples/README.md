# Does any of this actually help? — a measured A/B

> **Status: harness built and validated. Not yet run.** No generation has happened,
> so there are no results below to read. Everything here — tasks, graders, rubrics —
> was committed *before* any output existed. That is the point.

A hand-picked before/after transcript proves nothing and everyone knows it. This is
built so a skeptic can run it and get our numbers.

## Method

Two arms, same model (`claude-sonnet-5`), same temperature, same `max_tokens`.

- **Arm A** — task prompt + a neutral system prompt: *"You are a senior engineer. Write production-quality Python…"*
- **Arm B** — identical, plus the relevant `SKILL.md` appended.

Arm A is not a strawman. It gets the same "production code" framing and the same
effort. Weakening the control would make the whole exercise worthless.

`n = 5` per task per arm, fixed before running. 16 tasks → 80 generations per arm.

This tests whether the skill *content* changes behaviour. It deliberately does **not**
test triggering — whether a skill's `description` fires on the right task is a
separate property, measured separately (see *Triggering* below), because conflating
them lets a win in one hide a loss in the other.

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

**Tier 3 — cost.** Arm B carries roughly **57x** arm A's input tokens. That is a real
cost of using skills and goes in the headline table next to the quality delta. The
number that decides is cost per *passing* run, per `model-selection`.

## The five commitments

1. **Graders are pre-registered.** `graders/` was committed before any generation existed; git history proves it.
2. **Grading is blind.** Filenames are salted hashes; the rubric never receives the arm.
3. **No task reuses a skill's own example.** Otherwise it measures recall, not transfer.
4. **Every generation is published**, including the ugly ones.
5. **Losses stay in the headline table.** `naming-experiments.md` argues null results are the valuable half; a clean sweep reads as fabricated.

## Grader validation

A grader nobody tested is a number nobody should trust. Each rubric was validated
against hand-written naive/skilled fixture pairs in `fixtures/` before any run:

| Pair | Naive | Skilled |
|---|---|---|
| `t01` NL→SQL | 0.00 | 1.00 |
| `t09` query-DSL trap | 0.00 | 1.00 |
| `t13` architecture trap | 0.00 | 1.00 |
| `t08` **control** — prose summary | **1.00** | **0.00** (over-applied) |

The last row is the important one: the grader **can and will penalise the skills arm**.
That is what makes the outcome falsifiable rather than decorative.

Writing these fixtures found three real bugs in the graders — including a false
positive on `sql_is_safe`, the most consequential check — all before a cent was spent.

## Cost

Measured from real system-prompt sizes, not guessed:

| | Input tokens | Output tokens | Cost |
|---|---|---|---|
| Arm A (80 gens) | 6,958 | 120,000 | $1.21 |
| Arm B (80 gens) | 399,866 | 152,000 | $2.32 |
| Judge (optional) | — | — | ~$1.50 |
| **Total** | | | **~$5** |

## Running it

```bash
export ANTHROPIC_API_KEY=...
./examples/reproduce.sh          # N=5 by default
```

Or step by step:

```bash
python3 examples/run.py --arm a --n 5 --dry-run   # plan only, no API calls
python3 examples/run.py --arm a --n 5
python3 examples/run.py --arm b --n 5
python3 examples/grade.py                          # blind, writes results.tsv
```

## Triggering (separate experiment, not yet built)

Give a model only the 10 skill *descriptions*, plus the 16 task prompts and 10
unrelated ones ("refactor this CSS", "why is my Docker build slow"), and ask which
apply. Score precision and recall per skill. This catches a failure the main eval
cannot: a perfect skill whose description never matches is worth zero in production.

## Layout

```
examples/
├── tasks/tasks.py        # the 16 prompts
├── graders/checks.py     # 25 mechanical checks
├── graders/rubrics.py    # 51 per-task checks, each citing a skill line
├── fixtures/             # naive/skilled pairs proving the graders discriminate
├── run.py                # generator (needs a key)
├── grade.py              # blind grader -> results.tsv
└── reproduce.sh
```
