# Results

> **Status: no generation results published yet.** The harness is built, pre-registered, and validated in CI. Nothing has been run at a reportable sample size. This file will carry the headline numbers when it has been; until then it carries the method, so you can judge the method before there are numbers to argue with.

The claim these skills make is falsifiable: *installing them changes the code a coding agent writes, for the better, measurably.* This file is where that claim gets settled.

Full methodology and how to reproduce: **[examples/README.md](examples/README.md)**.
Generated reports, once runs exist: `examples/RESULTS.md` (scores) and `examples/TRIGGERING.md` (discovery). Both are written by the scripts below; neither is committed until there is something real in it.

## The design

| | |
|---|---|
| **Arm A** | Coding agent, no skills installed |
| **Arm B** | Same agent, same model, all 10 skills installed |
| **Tasks** | 16, phrased the way a user would phrase them — never naming the technique or the skill |
| **Task kinds** | `positive` (the skill should help), `trap` (the obvious answer is wrong), `control` (applying the skill is *itself* the error) |
| **Grading** | Deterministic AST and prose checks first, rubric-scored, blinded by filename hash |
| **Pre-registration** | Rubrics were written and fixture-validated before any run |

The control tasks are the point. A benchmark that only contains cases where your advice helps measures nothing. If these skills push an agent into building an agent loop for a task that needed one function call, the controls are where that shows up as a loss.

## What will be reported

Averages alone are not evidence. At n=3, `A = 0.67` vs `B = 0.83` is a hint, not a result. So the report gives:

- **Per-task scores**, never aggregate-only — a change that lifts the mean while breaking two tasks is a different decision than one that lifts everything
- **Mean and median**, with the raw per-task score lists visible
- **Number of runs** per task per arm
- **Win / tie / loss by task**, where a tie is a delta within 0.05 — rubric scores are means over a handful of binary checks, so exact equality is common and calling it a win would be an artifact
- **Bootstrap 95% confidence interval** on the mean delta: 10,000 resamples of the paired tasks under a fixed seed, so the interval is reproducible rather than a new number each run. The resampling unit is the *task*, not the run — runs of one task share a prompt and a rubric, and resampling them would narrow the interval by counting the same task twice
- **Effect size**, both Cohen's *d_z* across tasks and Cliff's delta within them, each named in the output, because a standardized mean difference and a rank-based measure fail in different ways at this sample size
- **Cost and effort** per arm — if arm B simply did more work, the gain may not be the skill

Shaped like this:

```text
Skill arm wins: 10
Ties:            3
Losses:          3

Mean score   A 0.61   B 0.78   delta +0.17
Bootstrap 95% CI  [+0.08, +0.25]
```

## The second measurement: did the skill even load?

A skill can fail two completely different ways, and collapsing them wastes the experiment:

- **Content failure** — the skill loaded and the output still didn't improve. The advice is wrong.
- **Discovery failure** — the skill never loaded. The advice is untested; the *description* is what failed.

So every run records which skills fired, and the report breaks results down by task: expected skill, triggered skill, whether the trigger was correct, and the outcome. That makes statements like *"the skill improves the agent by 18 percentage points when it triggers, but it only triggers 63% of the time"* possible — which turns a vague "do skills work?" into a concrete engineering problem: skill descriptions need optimization.

There is a dedicated benchmark for that half of the question — `examples/trigger_benchmark.py` — scoring discovery alone: precision, recall, F1, no-trigger rate, wrong-trigger rate.

## Reproducing it

```bash
python3 examples/setup_arms.py
python3 examples/run_arm.py --arm a --runs 3
python3 examples/run_arm.py --arm b --runs 3
python3 examples/check_contamination.py
python3 examples/grade.py
python3 examples/report.py
python3 examples/trigger_benchmark.py
```

Arm A must never see a skill; `check_contamination.py` verifies that rather than assuming it.

## Known threats to validity

Stated up front, because a results page that only lists its strengths isn't one:

- **Small n.** Per-task deltas smaller than the reported standard deviation are noise.
- **Harness overhead.** Both arms run inside a full coding-agent session with a large constant system prompt and a tool loop. Held constant across arms, but it widens variance relative to a single-turn API call.
- **Rubrics are proxies.** They are pre-registered and fixture-validated, but passing a deterministic check is not the same as being good code.
- **Task coverage is uneven.** All 10 skills are installed in arm B, but the 16 tasks target only 4 of them directly. The rest are exercised incidentally at best, so this measures those four, not the set.
- **Trigger detection is transcript-based.** A skill is counted as fired when the transcript shows it being invoked or read. A skill whose content influenced the output without leaving that trace is counted as not fired, which biases the fire rate down and the conditional gain up.
- **One model, one agent.** Results should not be assumed to transfer across models or harnesses until they've been run there.
