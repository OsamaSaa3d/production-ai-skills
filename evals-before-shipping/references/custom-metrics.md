# Custom Metrics and Judge Calibration

Built-in metrics cover generic quality. Anything specific to your domain needs a written criterion — and a judge you have checked against humans, because an uncalibrated judge is a random number with a decimal point.

## GEval: criteria in plain language

```python
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

policy_grounding = GEval(
    name="PolicyGrounding",
    criteria=(
        "Determine whether the actual output's claims about company policy "
        "are supported by the retrieval context. Penalize any policy statement "
        "not traceable to the context."
    ),
    evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
    threshold=0.8,
)
```

`evaluation_params` decides what the judge can see. Passing more than the criterion needs makes scores noisier and the judge more expensive — if the criterion is about grounding, the judge does not need the original input.

### Writing a criterion that scores consistently

**One dimension per metric.** A criterion covering correctness, tone, and grounding produces mush — a single number that moves for three unrelated reasons and tells you nothing about any of them.

```python
# BAD
criteria="Evaluate whether the response is accurate, well-written, and appropriately toned."

# GOOD — three metrics, each one dimension
accuracy  = GEval(name="Accuracy",  criteria="Determine whether every factual claim ...")
tone      = GEval(name="Tone",      criteria="Determine whether the response maintains ...")
grounding = GEval(name="Grounding", criteria="Determine whether each claim is traceable ...")
```

**Name what to penalize.** "Penalize any policy statement not traceable to the context" is scoreable. "Should be well-grounded" is not.

**Define the extremes.** Judges score more consistently when the ends of the scale are anchored:

```python
criteria=(
    "Determine whether the response correctly explains the refund policy.\n"
    "A perfect response states the exact window and the conditions that apply.\n"
    "A failing response states a window not in the context, omits a condition "
    "that changes the outcome, or hedges so heavily the user cannot act."
)
```

**Use the domain's vocabulary.** "Traceable to the context," "states the SLA," "names the responsible team" — concrete terms the judge can check, not abstractions it has to interpret.

## DAGMetric: when you need determinism

`GEval` is one judgment producing one score. `DAGMetric` is a decision tree, which is what you want when checks have a natural order or when part of the judgment is not subjective at all.

Use it when:

- **Order matters.** Check the format *before* judging the tone — a response in the wrong format should fail on format, not get a muddled tone score.
- **Part of the check is deterministic.** "Does it contain a ticket id" is a regex, not a judgment. Don't pay a judge for it.
- **Failures need distinct causes.** A tree tells you *which branch* failed; a single score does not.

```text
            ┌─ is it valid JSON? ──── no ──> score 0, reason "malformed"
            │        │ yes
            ├─ does it contain a decision field? ── no ──> score 0, reason "no decision"
            │        │ yes
            └─ is the decision justified by the context? ──> judge, 0–1
```

Start with `GEval`. Move to `DAG` when you need control, determinism, or a named failure branch. A `GEval` that scores 0.4 with the reason "the response was malformed" is a `DAG` you have not written yet.

## Calibration

**A judge you have not checked against human labels is not a measurement.** This is the step that gets skipped and the reason eval suites lose credibility.

### The procedure

**1. Label by hand.** 30–50 cases minimum. Score them yourself against the same criterion — ideally two people independently, so you find out whether the criterion is even clear to humans.

```python
HUMAN_LABELS = {
    "case_001": 1.0,   # clearly correct
    "case_002": 0.0,   # clearly wrong
    "case_003": 0.5,   # partially correct
}
```

Include boundary cases deliberately. A calibration set of obvious passes and obvious failures tells you nothing about where the judge actually fails: the middle.

**2. Run the judge and compare.**

```python
def calibrate(metric, cases, human_labels, tolerance=0.2):
    rows = []
    for case in cases:
        metric.measure(case)
        h = human_labels[case.id]
        rows.append({"id": case.id, "human": h, "judge": metric.score,
                     "delta": metric.score - h,
                     "agree": abs(metric.score - h) <= tolerance,
                     "reason": metric.reason})
    return rows
```

**3. Read the disagreements** — specifically `.reason` on each one. There are only three possibilities, and they have different fixes:

| The judge... | Fix |
|---|---|
| Applied a standard you didn't intend | Rewrite the criterion; name the thing it got wrong |
| Was right and the human label was wrong | Fix the label. This happens more than people expect. |
| Is inconsistent — same case, different scores | The criterion is ambiguous, or the judge model is too small |

**4. Measure agreement.** Aim for 80%+ within your tolerance. Below that, the criterion is the problem — not the judge model, and not a threshold you can tune your way out of.

**5. Re-calibrate** when you change the criterion, the judge model, or the thing being judged.

### While you are calibrating

```python
metric = GEval(..., threshold=None)     # score-only: computed and tracked, no pass/fail
```

`threshold=None` runs the metric without an opinion. Use it for anything you are still calibrating, so it accumulates data without gating CI on a number you do not yet trust.

For metrics you know are noisy but still want to see:

```python
metric = GEval(..., threshold=0.8, flaky=True)   # scored and reported, doesn't fail the case
```

`flaky=True` beats deleting a metric you are unsure about — you keep the signal without the false alarms.

Note: each `assert_test()` needs at least one non-flaky metric with a threshold, or nothing can fail.

## Judge model choice

Judge quality matters, but judging a binary assertion does not need your most expensive model.

```python
CHEAP  = "..."   # binary and near-binary judgments
STRONG = "..."   # nuanced criteria, trajectory metrics

format_ok = GEval(name="FormatOK", criteria="...", model=CHEAP)
reasoning = GEval(name="ReasoningQuality", criteria="...", model=STRONG)
```

Configure globally with `deepeval set-gemini`, `deepeval set-ollama --model=...`, `deepeval set-azure-openai ...`, or per metric with `model=`. Anthropic, LiteLLM, and custom `DeepEvalBaseLLM` subclasses all work.

**Calibrate the cheap judge before trusting it**, then keep it. This is the same descend-the-ladder move as `model-selection`, applied to the grader.

**Don't judge with the model under test** where you can avoid it. Self-preference is a real effect and it biases exactly the comparison you are trying to make.

## The five-metric cap

Two or three generic system metrics plus one or two custom criteria. More metrics means less signal, not more:

- Every metric is a judge call per case — cost and latency scale linearly.
- Ten metrics produce ten numbers nobody reads, and a suite nobody reads stops being run.
- Overlapping metrics move together, which looks like corroboration and is double-counting.

If you want a new metric, earn the slot: which existing one is it replacing?

## Reading results

Every metric returns `.score`, `.reason`, and `.is_successful()`. The score is the least informative of the three.

```python
for m in metrics:
    m.measure(test_case)
    if not m.is_successful():
        print(f"{m.__name__}: {m.score:.2f}\n  {m.reason}")
```

Turn on `verbose_mode=True` to see the judge's working on a sample.

**A score you haven't investigated is not a result.** A 0% pass rate on a frontier model almost always means the task or the grader is broken, not the model. A metric that passes everything is usually measuring nothing.
