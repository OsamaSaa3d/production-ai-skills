# Running the Suite in CI

An eval suite that runs only when someone remembers is not a test. This is how to make it a gate — without a bill nobody approved and without flaky failures that train the team to ignore red.

## The workflow

```yaml
name: evals
on:
  pull_request:
    paths: ["src/**", "prompts/**", "tools/**", "tests/evals/**"]

jobs:
  regression:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -r requirements.txt deepeval

      - name: Regression suite
        env:
          OPENAI_API_KEY: ${{ secrets.EVAL_JUDGE_KEY }}   # the judge, not your app's key
          APP_MODEL_KEY:  ${{ secrets.APP_MODEL_KEY }}
        run: deepeval test run tests/evals/test_regression.py -c

      - if: always()
        uses: actions/upload-artifact@v4
        with: {name: eval-results, path: .deepeval-cache/}
```

Three things worth copying:

**A separate judge key.** The judge model is not your app's model, and separating the keys means judge spend shows up as its own line item — which is what you will want when someone asks why the eval bill went up.

**Path filters.** A docs-only PR should not spend money on model calls.

**`timeout-minutes`.** A hung suite that burns thirty minutes of runner time on every PR gets disabled by someone within a week.

## Two suites, two jobs

They have opposite targets, so they cannot share a gate.

| | Regression | Capability |
|---|---|---|
| Contains | Everything the system already handles | Things it struggles with |
| Target | Near 100% | Low, rising over time |
| On failure | **Fail the build** | Report only |
| When | Every PR | Nightly or on demand |

```yaml
  capability:
    if: github.event_name == 'schedule'
    continue-on-error: true      # informational — a red here is not a broken build
    steps:
      - run: deepeval test run tests/evals/test_capability.py
```

Gating on the capability suite makes every PR red for things nobody broke. Not running it at all means you never find out the system got better. Nightly and informational is the right shape.

When a capability case becomes reliably solved, move it into the regression suite. That move is the record of progress.

## Cost control

The single most important flag:

```bash
deepeval test run tests/evals/test_regression.py -c     # cache: don't rerun passing cases
```

Cache passing cases and CI spends money only on what changed. On a large suite this is the difference between an eval gate and a budget conversation.

Other levers, in order of value:

| Lever | Saving |
|---|---|
| `-c` (cache passing cases) | Large — usually the majority |
| Cheap judge for binary criteria | Large; calibrate it once (`custom-metrics.md`) |
| Trajectory metrics on a subset | Large — these are the expensive metrics |
| Path filters on the workflow | Skips whole runs |
| Cap the suite at 5 metrics | Linear in metric count |
| Concurrency group cancelling superseded runs | Skips whole runs |

```yaml
concurrency:
  group: evals-${{ github.ref }}
  cancel-in-progress: true
```

Track judge spend as its own metric. An eval suite whose cost grows unnoticed gets cut in a budget review, and it is usually one metric or one un-cached job driving it.

## Flaky metrics

Model-based metrics are nondeterministic. Some variance is normal; the question is whether a failure is signal.

```python
tone = GEval(name="Tone", criteria="...", threshold=0.7, flaky=True)
```

`flaky=True` computes and reports the score but does not fail the test case. **Use it instead of deleting a metric you are unsure about** — you keep the trend line without training the team to ignore red.

`threshold=None` goes further: score-only mode, tracked with no pass/fail opinion. Right for anything still being calibrated.

Each `assert_test()` needs at least one non-flaky metric with a threshold, or nothing can fail — worth asserting in a meta-test if you use `flaky` liberally.

### Deciding whether a failure is real

Before adjusting a threshold, in this order:

1. **Read `.reason`.** Every metric returns it. Frequently it names a genuine regression, or a broken test case.
2. **Re-run the single case** a few times. Consistent failure is signal; alternating is variance.
3. **Check the deterministic metrics.** If `ToolCorrectnessMetric` failed, that is not flake — it is a comparison against ground truth.
4. **Only then** consider the threshold, and change it as a deliberate, reviewed commit with the reasoning in the message.

Lowering a threshold to make CI green is how a suite stops meaning anything. If you do it, say so in the commit.

## Reporting on the PR

A pass/fail is not enough to act on. Post the per-case diff:

```python
# tests/evals/report.py
def render(results, baseline):
    rows = ["| case | baseline | now | Δ |", "|---|---|---|---|"]
    for r in results:
        b = baseline.get(r.id)
        delta = "—" if b is None else f"{r.score - b:+.2f}"
        flag = " ⚠️" if b is not None and r.score < b - 0.05 else ""
        rows.append(f"| {r.id} | {b if b is not None else '—'} | {r.score:.2f} | {delta}{flag} |")
    return "\n".join(rows)
```

Report **per case, not just aggregate.** A change that lifts the pass rate four points while breaking two previously-passing cases is a different decision from a clean four-point lift, and the aggregate hides it.

Include alongside the scores: tokens per task, tool calls per task, and cost. A change that improves accuracy 2% while doubling tokens may be a net loss, and nobody will notice unless the number is on the PR.

## Pin the model

A suite is only valid against the model it was measured on.

```python
CONFIG = {
    "app_model": "claude-opus-5",        # pinned, not an alias
    "judge_model": "...",
    "suite_version": "regression@2026-09-14",
}
```

Prefer an explicit model ID over a moving alias for anything you regression-test against. An alias that silently advances turns your suite into a source of unreproducible failures.

**Treat a model change as a code change**: same PR, full re-run, per-case delta in the description. That applies to downgrades too — routing a step to a cheaper model to save cost is exactly the change most likely to regress something, and the suite is how you find out before users do.

## Production monitoring is the same suite, filtered

Referenceless metrics run unchanged on live traffic:

```python
PROD_METRICS = [
    AnswerRelevancyMetric(threshold=0.7),
    FaithfulnessMetric(threshold=0.9),
    ArgumentCorrectnessMetric(threshold=0.8),
    TaskCompletionMetric(threshold=0.7),
]
```

Reference-based metrics (`ToolCorrectnessMetric`, `ContextualRecallMetric`, `ContextualPrecisionMetric`) cannot — they need ground truth live traffic does not have. Split the list by environment in one place so the distinction is impossible to get wrong at a call site.

Sample rather than scoring everything, and alert on the **rate** over a window, not on individual failures. A single low score is noise; a rate moving from 2% to 9% is an incident.

Feed production failures back into the suite. That loop — real failure becomes a golden case — is what keeps a suite relevant, and it is the cheapest source of good test cases you have.

## Checklist

- [ ] Regression suite gates every PR touching prompts, tools, or agent code
- [ ] Capability suite runs nightly, informational only
- [ ] `-c` caching on, judge spend tracked separately
- [ ] Judge calibrated against human labels before any threshold gates CI
- [ ] Flaky metrics marked `flaky=True`, not deleted
- [ ] Per-case diff posted to the PR, with token and cost deltas
- [ ] App model and judge model pinned to explicit IDs
- [ ] Model changes re-run the full suite in the same PR
- [ ] Production failures flow back into the golden set
