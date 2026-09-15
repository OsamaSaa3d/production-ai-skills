# Results

The claim these skills make is falsifiable: *installing them changes the code a coding agent writes, for the better, measurably.* This file is where that claim gets settled.

## Run 1 — 2026-09-15

`claude-sonnet-5` at high effort in headless Claude Code, 16 tasks × 3 runs × 2 arms = 96 generations. Arm A's control held: 48 of 48 runs came back clean from the contamination check.

```text
Skill arm wins: 12
Ties:            4
Losses:          0

Mean score   A 0.40   B 0.76   delta +0.36
Bootstrap 95% CI  [+0.22, +0.51]
Controls: no negative delta (t04 +0.50, t08 0.00, t12 +0.17)
Skill fired in 39/48 arm-B runs (81%) · precision 0.87 · recall 0.85
Effort: B used slightly fewer turns and tool calls, ~4% more cost
```

What that supports, and what it doesn't:

- **The skills helped on the 4 skills the tasks target**, and no answer got worse on average. The other 6 skills were not tested.
- **A third to a half of the gain is style.** Arm B wrote hand-written strict schemas the way the skills prescribe. Arm A often used the SDK's `@beta_tool` runner, which is valid but fails those checks. Without the four style checks the delta is **+0.20**, and the t12 control ("add one tool") goes to **−0.33**.
- **The gains that don't depend on style are architectural:**
  - task-shaped tools instead of one tool per endpoint (t10)
  - a workflow instead of an agent loop for a fixed pipeline (t14)
  - typed search fields instead of a query grammar (t09)
  - extraction that handles refusal and missing fields (t05)
  - stopping conditions on a genuine agent (t16)
- **Install first:** `tool-design`, `agent-vs-workflow-decision`, then `structured-output`.
- **A content defect it exposed:** on t11, `tool-design` fired every time and jumped straight to decomposing the tool, skipping the "measure first" step the skill itself asks for.
- **Two tasks measured nothing** (t07, t15). They refer to inputs that don't exist in an empty directory, so both arms asked for them instead of writing code.
- **Three grader bugs were fixed after generation**, on both arms. Before the fixes the headline was 12/3/1, +0.30 [+0.15, +0.44].

**Full write-up, per-task tables, sensitivity analysis and threats to validity: [examples/RESULTS.md](examples/RESULTS.md).** Discovery: [examples/TRIGGERING.md](examples/TRIGGERING.md). Every generation and transcript is committed under `examples/runs/`.

Full methodology and how to reproduce: **[examples/README.md](examples/README.md)**.

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

## What the report gives

Averages alone are not evidence. At n=3, `A = 0.67` vs `B = 0.83` is a hint, not a result. So the report gives:

- **Per-task scores**, never aggregate-only — a change that lifts the mean while breaking two tasks is a different decision than one that lifts everything
- **Mean and median**, with the raw per-task score lists visible
- **Number of runs** per task per arm
- **Win / tie / loss by task**, where a tie is a delta within 0.05 — rubric scores are means over a handful of binary checks, so exact equality is common and calling it a win would be an artifact
- **Bootstrap 95% confidence interval** on the mean delta: 10,000 resamples of the paired tasks under a fixed seed, so the interval is reproducible rather than a new number each run. The resampling unit is the *task*, not the run — runs of one task share a prompt and a rubric, and resampling them would narrow the interval by counting the same task twice
- **Effect size**, both Cohen's *d_z* across tasks and Cliff's delta within them, each named in the output, because a standardized mean difference and a rank-based measure fail in different ways at this sample size
- **Cost and effort** per arm — if arm B simply did more work, the gain may not be the skill


## The second measurement: did the skill even load?

A skill can fail two completely different ways, and collapsing them wastes the experiment:

- **Content failure** — the skill loaded and the output still didn't improve. The advice is wrong.
- **Discovery failure** — the skill never loaded. The advice is untested; the *description* is what failed.

So every run records which skills fired, and the report breaks results down by task: expected skill, triggered skill, whether the trigger was correct, and the outcome. That makes statements like *"the skill improves the agent by 18 percentage points when it triggers, but it only triggers 63% of the time"* possible — which turns a vague "do skills work?" into a concrete engineering problem: skill descriptions need optimization.

There is a dedicated benchmark for that half of the question — `examples/trigger_benchmark.py` — scoring discovery alone: precision, recall, F1, no-trigger rate, wrong-trigger rate.

## Reproducing it

```bash
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
