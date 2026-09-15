# Results — skills A/B, run 1

> **Read this section first.** It is written by hand from the generated tables further
> down; everything from "Generated tables" on is `report.py` output, unedited.
> Run: 2026-09-15 · `claude-sonnet-5`, effort `high`, Claude Code 2.1.271 headless ·
> n = 3 per task per arm, 96 generations · skills as of commit `e470e2e` (v1.0).

## Verdict

**The skills helped on the four skills the tasks target, and made no answer worse on
average.** Arm B won 12 of 16 tasks, tied 4, lost 0. Mean score 0.40 → 0.76 (delta
**+0.36**, bootstrap 95% CI **[+0.22, +0.51]**).

Read the gain for what it is. A third to a half of it is arm B writing code *the way
the skills prescribe*: hand-written tool schemas with `strict: true` and
`additionalProperties: false`. Arm A often used the Anthropic SDK's `@beta_tool` tool
runner instead, which is a legitimate native approach that the rubrics score as a fail.
Drop those four style checks and the delta is **+0.20** (see *Sensitivity*).

The effects that survive without the style checks are the ones that matter most:
- consolidating 14 endpoints into task-shaped tools (t10, +1.00)
- not building an agent loop for a fixed pipeline (t14, +0.50)
- handling refusal, truncation and nullable fields in extraction (t05, +0.56)
- a real stopping condition on a genuine agent (t16, +0.44)
- typed search fields instead of a query grammar (t09, +0.33)

**Which to install first:** `tool-design` and `agent-vs-workflow-decision`. They carry
the architecture decisions arm A got wrong, and their gains don't come from style
checks. Then `structured-output`. `llm-tool-calling` also scored large wins, but mostly
on style checks, so its content effect is the least certain of the four.

**Six skills were not tested.** The 16 tasks target 4 skills. This run says nothing about
`context-and-memory`, `evals-before-shipping`, `model-selection`,
`rag-pipeline-standard`, `subagents-and-multi-agent` or `system-prompt-engineering`.

## How the scores are made

Every number in this file comes from the same five steps. None of them uses an LLM
judge, and the grader never sees which arm an answer came from.

### 1. One session → one answer

For each task, each arm, each run:
- A fresh, empty directory is created. In arm B, all ten skills are copied into its
  `.claude/skills/`.
- `claude -p "<task prompt>"` runs there headless (`examples/run_arm.py`).
- The **answer** is the session's final message, plus the text of every file it wrote
  into the directory. Sessions often put the code in a file and reply with a summary,
  and the code is what gets graded.

16 tasks × 3 runs × 2 arms = **96 answers**. Each is saved under a salted hash filename
(`runs/a/`, `runs/b/`), so a filename doesn't reveal the arm.

### 2. Answer → a list of pass/fail checks

Each task has a **rubric**: a short list of mechanical checks (`graders/rubrics.py`,
implemented in `graders/checks.py`). A check is one of two kinds:
- **AST:** parse the Python in the answer's code blocks and look for a structure, such as
  a dict literal with `name` and `input_schema`, `strict=True`, or a `while` loop whose
  condition reads `stop_reason`.
- **Regex:** search the text for a pattern, such as a framework import, or the answer
  saying a workflow is enough.

Each check cites the line of the skill it is testing. Before grading, run-directory paths
are removed from the answer, so the arm can't leak through a path.

| task | kind | the checks (all must pass for 1.00) |
|---|---|---|
| t01 orders Q&A over Postgres | positive | native tool schema · `strict` on · `additionalProperties: false` · no framework · tool result sent back as a tool message · tool errors returned as data · model never writes the executed SQL |
| t02 refund bot loop | positive | native tool schema · `strict` · tool result message · errors as data · iteration cap · no framework |
| t03 wrap two Python functions | positive | native tool schema · `strict` · `additionalProperties: false` · no framework · tool result message |
| t04 add a step inside LangGraph | **control** | **keeps LangGraph** · `strict` on the new tool |
| t05 invoice extraction | positive | nullable optional fields · handles refusal/truncation · `additionalProperties: false` · no framework |
| t06 email urgency classifier | positive | enum for the label · reasoning field before the label · handles refusal/truncation · no framework |
| t07 contract clauses for legal | positive | nullable fields · handles refusal/truncation · mentions cost/trade-off |
| t08 meeting summary paragraph | **control** | **no JSON schema forced onto prose** |
| t09 ticket search with a query DSL | **trap** | model fills typed fields, not a query string · enums for bounded fields · query built in code · native tool schema |
| t10 expose a 14-endpoint CRM | positive | fewer tools than endpoints (or says so) · native tool schema |
| t11 agent inverts `mode` | positive | says to measure/eval before splitting · mentions the cost of more tools |
| t12 one fetch-user tool | **control** | **no tool-search / deferred-loading / examples ceremony** · native tool schema |
| t13 daily CSV → email | **trap** | says a workflow/script is enough · **no** model-driven loop |
| t14 bug-report triage | **trap** | says a workflow is enough · **no** model-driven loop |
| t15 competitor research brief | positive | mentions cost/trade-off · has a stopping condition |
| t16 fix a failing test | positive | model-driven loop present · stopping condition · mentions cost |

The **bold** checks are the ones where "applying the skill" is the wrong move. On a
control, the pass is holding back. On the two workflow traps (t13, t14),
`model_driven_loop` is **inverted**: finding an agent loop is a fail.

### 3. Checks → a run score

**Run score = checks passed ÷ checks in the rubric**, between 0 and 1.

Worked examples, taken from the actual data:

| run | checks passed | run score |
|---|---|---|
| t01, arm A, run 0 | no framework ✓, errors as data ✓, SQL safe ✓; native schema ✗, strict ✗, additionalProperties ✗, tool message ✗ | 3/7 = **0.43** |
| t01, arm B, run 0 | all 7 ✓ | 7/7 = **1.00** |
| t14, arm A, run 0 | didn't say "workflow" ✗; built an agent loop ✗ (inverted) | 0/2 = **0.00** |
| t14, arm B, run 1 | didn't say "workflow" ✗; no agent loop ✓ | 1/2 = **0.50** |
| t06, arm B, run 0 | enum ✓, reasoning first ✓, refusal handled ✓, no framework ✓ | 4/4 = **1.00** |

Rubrics are short, so scores move in big steps. On a 2-check rubric a run can only score
0, 0.5 or 1.

### 4. Run scores → a task delta

- **Task mean** for an arm is the mean of its 3 run scores. Arm A on t14 is
  (0.00 + 0.50 + 0.50) / 3 = 0.33, and arm B is (1.00 + 0.50 + 1.00) / 3 = 0.83.
- **Delta** = B mean − A mean = +0.50 for t14. A positive delta means the skills arm
  scored higher.
- **Win / tie / loss:** a task counts as a *tie* if |delta| < 0.05, otherwise a win or a
  loss. The threshold exists because the smallest real difference on the longest rubric
  is 1/7 ≈ 0.14. Anything under 0.05 is one check flipping in a single run.

### 5. Task deltas → the headline

- **Mean score / mean delta:** the mean over the 16 task means. Each task counts once,
  however many checks it has.
- **Median:** the same, using the middle value. It isn't pulled around by one task at
  0 or 1.
- **95% confidence interval [+0.22, +0.51]:** a bootstrap. Draw 16 tasks from the 16
  with replacement, take the mean delta, repeat 10,000 times, and keep the middle 95%.
  The seed is fixed, so the interval is reproducible. It resamples *tasks*, not runs,
  because runs of the same task aren't independent. Plain reading: if a similar set of
  tasks were run again, the true gain would plausibly fall anywhere between +0.22 and
  +0.51. It is clearly above zero, but the exact size is uncertain.
- **Cohen's d_z = +1.18:** mean delta ÷ standard deviation of the deltas. Above 0.8 is
  conventionally "large". With only 16 coarse deltas, read it as "the direction is
  consistent" rather than as a precise size.
- **Cliff's delta = +0.61 ("large"):** within each task, compare every arm-B run with
  every arm-A run. It is P(B higher) − P(A higher), averaged over tasks, and ranges from
  −1 to +1. It makes no assumption about how scores are distributed, which matters for
  scores that cluster at 0 and 1.

### Triggering numbers

These come from the session transcripts, not the answers. A skill counts as **fired**
when the session called the `Skill` tool on it or read its `SKILL.md`.
- **Fire rate:** runs where any repo skill fired ÷ arm-B runs.
- **Precision:** correct loads ÷ all loads.
- **Recall:** runs where the intended skill fired ÷ runs.

Both precision and recall are computed on the positives and traps. Controls are excluded,
because silence is correct there.

### What a score is not

A score of 1.00 means *every check on that rubric passed*, not that the code is
production-ready. A 0.00 can mean bad code, or no code at all: t07 and t15 scored 0 in
both arms because the sessions asked for missing inputs. The checks are proxies chosen to
test specific claims the skills make. The *Sensitivity* section below shows how much the
headline depends on which proxies you count.

## Controls: where the skills could lose

No control task has a negative delta. That is the most important result in this file.

| control | what over-application looks like | A | B | delta | note |
|---|---|---|---|---|---|
| t04 keep LangGraph | ripping out a load-bearing framework | 0.50 | 1.00 | +0.50 | both arms kept LangGraph 3/3; B also set `strict` |
| t08 prose summary | forcing a JSON schema on a paragraph | 1.00 | 1.00 | 0.00 | both correct 3/3; no skill fired, which is correct |
| t12 one trivial tool | tool-search / deferred-loading ceremony | 0.67 | 0.83 | +0.17 | B added ceremony in 1/3 runs; A in 0/3 |

t12 is the one place over-application showed: `minimal_for_trivial_tool` passed 3/3 in
arm A and 2/3 in arm B, and only the native-schema check put B ahead. Without the style
checks t12 is **−0.33** (see *Sensitivity*). At n=3 that is a signal to watch, not a
settled finding.

## By kind

| kind | tasks | mean delta | W/T/L |
|---|---|---|---|
| positive | 10 | +0.40 | 7/3/0 |
| trap | 3 | +0.36 | 3/0/0 |
| control | 3 | +0.22 | 2/1/0 |

## Triggering

A skill fired in **39 of 48** arm-B runs (81%). On the positives and traps, precision is
0.87 and recall 0.85 ([TRIGGERING.md](TRIGGERING.md)).

- **Nothing fired in 9 runs:** t07, t08 and t15. t08 is a control, so silence is right.
  t07 and t15 are task defects rather than description failures (see *Threats*).
- **An unrelated skill fired in 7 runs:** mostly `llm-tool-calling` loading alongside
  the right skill. On the t12 control it loaded *instead of* `tool-design` in 2 of 3 runs.
- **Gain when a skill fired:** +44 pp on the tasks where one could fire, the same as
  across all runs on those tasks. A skill fired in every run on those tasks, so this run
  can't tell description quality apart from content quality.

## Effort

| arm | mean turns | mean tool calls | mean cost / run |
|---|---|---|---|
| A | 12.3 | 10.7 | $0.354 |
| B | 11.9 | 9.9 | $0.369 |

Arm B did not do more work: slightly fewer turns and tool calls, and about 4% more cost
(the skill text in context). The gain is not an effort artifact.

## Sensitivity: how much is style?

Arm A's sessions often used `@beta_tool` with the SDK tool runner. Several pre-registered
checks don't recognise that path:
- `uses_native_tool_calling` requires a hand-written schema literal
- `tool_result_role` requires an explicit tool-result message
- `strict_mode_on` and `additional_properties_false` require flags that the runner path
  doesn't show

13 arm-A runs used `@beta_tool` without a literal schema. Those checks cite real skill
lines, so they stay in the rubrics. But they measure conformance to the skill's
preferred style as much as correctness.

| checks included | mean delta |
|---|---|
| all (pre-registered) | +0.36 |
| without `uses_native_tool_calling`, `tool_result_role` | +0.30 |
| also without `strict_mode_on`, `additional_properties_false` | +0.20 |

Without the style checks, t01, t03 and t04 drop to 0.00, and the t12 control drops to
−0.33. The headline tables keep the pre-registered rubrics. This table is here so nobody
has to take the headline on trust.

## Content findings worth acting on

- **t11: `tool-design` fired in all 3 runs and went straight to its remedy.** The task
  was an agent that keeps getting `mode` backwards. Every arm-B run split the tool into
  `filter_records_including_value` and `filter_records_excluding_value`. Arm A instead
  treated it as a handler bug and fixed the branches. Both arms score 0.00. This is
  **ambiguous, not a clear skill defect**. The prompt reports an observed failure, and the
  skill says to decompose when the agent demonstrably gets the flag wrong, so arm B
  followed its trigger. What no arm-B run did was what the rubric asks for: confirm the
  failure with an eval, rule out a plain implementation bug, and note that more tools
  cost selection accuracy. The skill could say "a user report is not a measurement"
  more explicitly. `SKILL.md` was left unchanged: n=3 and one task don't justify an edit.
- **t12: `llm-tool-calling` fires on "add one tool".** In one of three runs, the answer
  carried ceremony a single tool doesn't need.

## Threats to validity

- **n = 3.** Per-task deltas smaller than the run sd are noise. t09 (B sd 0.38), t12 and
  t16 are the least stable.
- **Style vs substance.** The pre-registered rubrics reward the skills' preferred idiom,
  and arm A's idiom was a valid alternative (see *Sensitivity*).
- **Two tasks measured nothing.** t07 ("pull the party names … out of *these contracts*")
  and t15 (research "*our* competitors") refer to inputs that don't exist in an empty
  directory. In all 12 runs across both arms, the session asked for the documents or the
  company instead of writing code, and scored 0. These ties come from task defects, and
  they pull both arms' means down.
- **Deviation: a non-interactive note.** In a pilot, a word-for-word prompt in an empty
  directory got clarifying questions and no code. So both arms ran with the same appended
  system prompt: *"This is a non-interactive session: nobody can answer questions. Make
  reasonable assumptions, state them briefly, and deliver working code."* It names no
  skill or technique, and the task prompt itself was passed word for word. The one pilot
  run was discarded.
- **Deviation: isolation.** Instead of two shared arm directories, each run got its own
  fresh empty directory (`run_arm.py`). Sessions ran with `--setting-sources project` and
  `--strict-mcp-config`, and with claude.ai MCP servers disabled, so no user plugins,
  global CLAUDE.md or MCP servers reached either arm. Arm A ran to completion before any
  arm-B directory existed.
- **Three grader fixes after generation.** Each was applied to both arms, and both arms
  were re-graded. All 16 rubrics still separate their fixtures.
  1. Code blocks were matched to each other by position. In answers that also had
     `md` or `json` blocks, the session's actual code became invisible to the AST checks.
  2. `no_forced_schema_on_prose` read `output_config={"effort": ...}` as a schema and
     failed all six correct t08 answers.
  3. Answers repeat their run path (`…/skills-eval/arm-a/t11-r0`). That told the grader
     which arm it was reading. The "eval" in the path also passed
     `measures_before_decomposing` in 2 arm-A runs that never mentioned measuring. Paths
     are now redacted before grading.

  Before the fixes: W/T/L 12/3/1, delta +0.30 [+0.15, +0.44], with t11 a loss. After:
  12/4/0, +0.36 [+0.22, +0.51]. Fix 1 moved scores in both directions: it *lowered*
  arm A on t14 by exposing a loop the old parser missed.
- **Contamination.** One arm-A run (t14 r2) was flagged for the phrase "structured-output
  call". Its transcript showed no access to the repository, but per the brief it was
  discarded and re-run, and the re-run is clean. Final check: 48/48 clean.
- **Interrupted runs.** Usage limits and memory pressure stopped sessions partway through
  the queue. Those runs produced no answer and were re-run. No answer was ever read and
  then discarded, so no run was re-rolled for a better score.
- **Capture.** An answer is the session's final message plus the files it wrote. A
  capture bug first swept virtualenvs (up to 40 MB) into three arm-A answers. They were
  re-captured from the untouched run directories before grading, but git history still
  contains the bloated versions.
- **Skills changed during the run.** Commit `e470e2e` edited all ten `SKILL.md` files
  while arm A was running. Arm A has no skills, so it's unaffected. All of arm B ran
  against the edited version.
- **One model, one harness, one day.** Don't assume these results hold for other models
  or agents until the eval is run there.

---

# Generated tables

Generated by `examples/report.py`. Per task, never aggregate-only.

## Headline

```
Skill arm wins: 12
Ties:           4
Losses:         0

Mean score (task-weighted)
  A      0.40
  B      0.76
  delta  +0.36

Median per-task score
  A      0.38
  B      0.92
  delta  +0.35

Bootstrap 95% CI on the mean delta: [+0.22, +0.51]
  10000 resamples of the 16 paired tasks, random.Random(20260201)

Effect size
  Cohen's d_z (paired, across tasks)   +1.18
  Cliff's delta (within task, meaned)  +0.61  (large)
```

16 of 16 tasks have runs in both arms (48 arm-A runs, 48 arm-B runs). Every aggregate here is **task-weighted** — each task contributes its own per-run mean once — so a task that got five runs cannot outvote one that got three.

A task counts as a **tie** when |delta| < 0.05. A rubric score is the mean of a handful of binary checks, so one check on the widest rubric moves a single run by 0.14: any delta from a *consistent* difference between the arms clears 0.05 easily, and anything under it is one check flipping in a minority of runs.

The interval is a **percentile bootstrap resampling tasks, not runs**. Runs of one task share a prompt and a rubric, so they are not independent draws and resampling them would narrow the interval by counting the same task twice. Because the 16 tasks were hand-picked rather than sampled, the interval describes uncertainty from this task mix and from run noise — not from any population of "all coding tasks". Seed and resample count are fixed in `evalstats.py` so the published interval is reproducible.

Two effect sizes, because neither is sufficient alone. **Cohen's d_z** is the paired standardised mean difference over per-task deltas, which is the effect size that matches how the delta was computed; it also assumes a spread that a dozen clumped 0–1 scores do not really have. **Cliff's delta** is distribution-free — the chance a random arm-B run beats a random arm-A run on the same task, minus the reverse — computed within each task so task difficulty cannot drive it. At this n both are indicative only: with 16 paired tasks the ranking of tasks is stable long before the magnitude is, and a d_z above 1 should be read as "the sign is probably right", not as a measured size.

## Per task

| task | kind | skill | A mean | A sd | B mean | B sd | delta | verdict | n (A/B) | fired |
|---|---|---|---|---|---|---|---|---|---|---|
| t01 | positive | llm-tool-calling | 0.43 | 0.00 | 1.00 | 0.00 | +0.57 | win | 3/3 | 3/3 |
| t02 | positive | llm-tool-calling | 0.67 | 0.29 | 0.94 | 0.10 | +0.28 | win | 3/3 | 3/3 |
| t03 | positive | llm-tool-calling | 0.20 | 0.00 | 1.00 | 0.00 | +0.80 | win | 3/3 | 3/3 |
| t04 | control | llm-tool-calling | 0.50 | 0.00 | 1.00 | 0.00 | +0.50 | win | 3/3 | 3/3 |
| t05 | positive | structured-output | 0.33 | 0.14 | 1.00 | 0.00 | +0.67 | win | 3/3 | 3/3 |
| t06 | positive | structured-output | 0.58 | 0.14 | 0.83 | 0.14 | +0.25 | win | 3/3 | 3/3 |
| t07 | positive | structured-output | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | tie | 3/3 | 0/3 |
| t08 | control | structured-output | 1.00 | 0.00 | 1.00 | 0.00 | +0.00 | tie | 3/3 | 0/3 |
| t09 | trap | tool-design | 0.33 | 0.14 | 0.75 | 0.25 | +0.42 | win | 3/3 | 3/3 |
| t10 | positive | tool-design | 0.00 | 0.00 | 1.00 | 0.00 | +1.00 | win | 3/3 | 3/3 |
| t11 | positive | tool-design | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | tie | 3/3 | 3/3 |
| t12 | control | tool-design | 0.67 | 0.29 | 0.83 | 0.29 | +0.17 | win | 3/3 | 3/3 |
| t13 | trap | agent-vs-workflow-decision | 0.83 | 0.29 | 1.00 | 0.00 | +0.17 | win | 3/3 | 3/3 |
| t14 | trap | agent-vs-workflow-decision | 0.33 | 0.29 | 0.83 | 0.29 | +0.50 | win | 3/3 | 3/3 |
| t15 | positive | agent-vs-workflow-decision | 0.00 | 0.00 | 0.00 | 0.00 | +0.00 | tie | 3/3 | 0/3 |
| t16 | positive | agent-vs-workflow-decision | 0.44 | 0.19 | 0.89 | 0.19 | +0.44 | win | 3/3 | 3/3 |

## Per-task spread

Every graded run, not only its mean. Two runs at 1.00 and one at 0.00 is a different finding from three at 0.67, and the mean cannot tell them apart.

| task | n (A/B) | A scores | A median | B scores | B median |
|---|---|---|---|---|---|
| t01 | 3/3 | 0.43, 0.43, 0.43 | 0.43 | 1.00, 1.00, 1.00 | 1.00 |
| t02 | 3/3 | 0.83, 0.83, 0.33 | 0.83 | 1.00, 1.00, 0.83 | 1.00 |
| t03 | 3/3 | 0.20, 0.20, 0.20 | 0.20 | 1.00, 1.00, 1.00 | 1.00 |
| t04 | 3/3 | 0.50, 0.50, 0.50 | 0.50 | 1.00, 1.00, 1.00 | 1.00 |
| t05 | 3/3 | 0.25, 0.25, 0.50 | 0.25 | 1.00, 1.00, 1.00 | 1.00 |
| t06 | 3/3 | 0.75, 0.50, 0.50 | 0.50 | 0.75, 1.00, 0.75 | 0.75 |
| t07 | 3/3 | 0.00, 0.00, 0.00 | 0.00 | 0.00, 0.00, 0.00 | 0.00 |
| t08 | 3/3 | 1.00, 1.00, 1.00 | 1.00 | 1.00, 1.00, 1.00 | 1.00 |
| t09 | 3/3 | 0.50, 0.25, 0.25 | 0.25 | 1.00, 0.75, 0.50 | 0.75 |
| t10 | 3/3 | 0.00, 0.00, 0.00 | 0.00 | 1.00, 1.00, 1.00 | 1.00 |
| t11 | 3/3 | 0.00, 0.00, 0.00 | 0.00 | 0.00, 0.00, 0.00 | 0.00 |
| t12 | 3/3 | 0.50, 0.50, 1.00 | 0.50 | 1.00, 1.00, 0.50 | 1.00 |
| t13 | 3/3 | 1.00, 0.50, 1.00 | 1.00 | 1.00, 1.00, 1.00 | 1.00 |
| t14 | 3/3 | 0.00, 0.50, 0.50 | 0.50 | 1.00, 0.50, 1.00 | 1.00 |
| t15 | 3/3 | 0.00, 0.00, 0.00 | 0.00 | 0.00, 0.00, 0.00 | 0.00 |
| t16 | 3/3 | 0.33, 0.67, 0.33 | 0.33 | 1.00, 0.67, 1.00 | 1.00 |

## By task kind

The controls are where skills can *lose*: there the correct behaviour is not to apply the skill. A negative delta on a control is the most important number in this file.

| kind | tasks | mean delta | median delta | worst task delta | W/T/L |
|---|---|---|---|---|---|
| positive | 10 | +0.40 | +0.36 | +0.00 | 7/3/0 |
| trap | 3 | +0.36 | +0.42 | +0.17 | 3/0/0 |
| control | 3 | +0.22 | +0.17 | +0.00 | 2/1/0 |

## Triggering

A skill fired in **39 of 48** arm-B runs (81%). Of those runs: 32 loaded the intended skill and nothing else, 5 loaded it alongside another, 2 loaded only an unrelated one, 9 loaded nothing.

A skill that never loads is worth zero in production no matter how good its content is, and the two failures need opposite fixes — a better description, or better content. `trigger_benchmark.py` scores discovery on its own, with precision and recall; this section is the joint view against the scores.

Over the **13** task(s) with runs in both arms where a skill fired at least once: arm B gains **+44 percentage points** on the runs where a skill actually fired, against **+44 pp** across all of its runs on **those same tasks** — the two figures cover one task set on purpose, because comparing a conditional mean to a mean over a different set of tasks is not a comparison. Across all 16 paired task(s), including the 3 where no skill ever fired, the gain is **+36 pp**, and a skill fired in **81%** of arm-B runs.

The conditional figure is the ceiling the descriptions are currently throwing away. It is not the number to quote as the skill's effect: conditioning on firing also conditions on the agent having recognised the task, and those are the runs where it was most likely to do well anyway.

| task | expected skill | triggered skill(s) | trigger correct? | outcome |
|---|---|---|---|---|
| t01 | llm-tool-calling | llm-tool-calling (3/3) | 3/3 | fired and helped (+0.57) |
| t02 | llm-tool-calling | llm-tool-calling (3/3) | 3/3 | fired and helped (+0.28) |
| t03 | llm-tool-calling | llm-tool-calling (3/3) | 3/3 | fired and helped (+0.80) |
| t04 | llm-tool-calling *(control: none wanted)* | llm-tool-calling (3/3) | 3/3 | restrained (+0.50) |
| t05 | structured-output | structured-output (3/3) | 3/3 | fired and helped (+0.67) |
| t06 | structured-output | structured-output (3/3) | 3/3 | fired and helped (+0.25) |
| t07 | structured-output | none (3/3) | 0/3 | discovery failure — no skill ever loaded (+0.00) |
| t08 | structured-output *(control: none wanted)* | none (3/3) | 3/3 | discovery failure — no skill ever loaded (+0.00) |
| t09 | tool-design | tool-design (3/3) | 3/3 | fired and helped (+0.42) |
| t10 | tool-design | tool-design (3/3), llm-tool-calling (1/3) | 3/3 | fired and helped (+1.00) |
| t11 | tool-design | tool-design (3/3) | 3/3 | content failure — fired, no gain (+0.00) |
| t12 | tool-design *(control: none wanted)* | llm-tool-calling (3/3), tool-design (1/3) | 1/3 | restrained (+0.17) |
| t13 | agent-vs-workflow-decision | agent-vs-workflow-decision (3/3) | 3/3 | fired and helped (+0.17) |
| t14 | agent-vs-workflow-decision | agent-vs-workflow-decision (3/3), structured-output (1/3), llm-tool-calling (1/3) | 3/3 | fired and helped (+0.50) |
| t15 | agent-vs-workflow-decision | none (3/3) | 0/3 | discovery failure — no skill ever loaded (+0.00) |
| t16 | agent-vs-workflow-decision | agent-vs-workflow-decision (3/3), llm-tool-calling (2/3) | 3/3 | fired and helped (+0.44) |

## Effort check

If arm B simply did more work, the gain may not be the skill.

| arm | runs | mean turns | mean tools/run | mean cost usd |
|---|---|---|---|---|
| a | 48 | 12.3 | 10.7 | 0.354 |
| b | 48 | 11.9 | 9.9 | 0.369 |

## Threats to validity

- Both arms run inside a Claude Code session, which carries a large constant system prompt and a tool loop. That is held constant, but it widens variance relative to a single-turn API call.
- n is small. Treat per-task deltas smaller than the reported sd as noise.
- The bootstrap interval assumes the paired tasks are exchangeable. They are not a random sample of anything — they were written to probe specific failure modes, including three controls chosen to make the skills lose. The interval bounds sampling noise within this task set and nothing wider.
- Effect sizes at 16 paired task(s) are indicative. d_z in particular is unstable when the per-task deltas are few and coarse; a large value can come from small spread rather than a large effect.
- The win/tie/loss split depends on the 0.05 tie tolerance documented above. A different tolerance moves tasks between the columns; the per-task table is the record, not the counts.
- Triggering is detected from the transcript (a `Skill` call or a read of a `SKILL.md`), so a session that absorbed a description without loading the file counts as not fired. That biases the fire rate down, not up.
- Arm B is the only arm with skills installed; nothing else differs. `check_contamination.py` verifies arm A never read one.
- Grader rubrics were pre-registered and are validated against fixtures (`validate_graders.py`), but they are still proxies for code quality.
