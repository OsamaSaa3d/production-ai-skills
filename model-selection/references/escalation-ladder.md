# Wiring the Ladder Into the Eval Harness

Phase 1 established a reference implementation passing at a known rate on the strongest model. Phase 2 walks down the cost ladder, comparing each candidate against the **target** rather than against a guess. This is that walk, as code, including the case nobody plans for: no candidate passes.

## The ladder

```python
@dataclass
class Rung:
    model_id: str
    cost_per_task: float
    caps: Capabilities

def build_ladder(matrix, profile, min_context) -> list[Rung]:
    """Capability gate first, then sort by cost per task. Never the reverse."""
    usable_models = [c for c in matrix if usable(c, min_context)]
    rungs = [Rung(c.model_id, cost_per_successful_task(c, profile), c)
             for c in usable_models]
    return sorted(rungs, key=lambda r: r.cost_per_task)
```

The gate is not a preference. A cheaper model that cannot do strict tool calling is not a cheaper option — it is a broken one, and it will fail silently rather than loudly. See `capability-matrix.md`.

## The descent

```python
@dataclass
class Selection:
    model_id: str
    pass_rate: float
    cost_per_task: float
    saving_vs_reference: float
    interface_fixes_applied: list[str]
    rejected: list[tuple[str, float]]     # every candidate tried, and its score

def descend(ladder, suite, *, target, reference) -> Selection:
    rejected = []
    for rung in ladder:
        if rung.cost_per_task >= reference.cost_per_task:
            break                                   # nothing cheaper left to try
        result = suite.run(rung.model_id)
        if result.pass_rate >= target:
            return Selection(rung.model_id, result.pass_rate, rung.cost_per_task,
                             reference.cost_per_task - rung.cost_per_task, [], rejected)
        rejected.append((rung.model_id, result.pass_rate))
    return Selection(reference.model_id, reference.pass_rate, reference.cost_per_task,
                     0.0, [], rejected)
```

**Compare against `target`, not against `reference`.** A cheaper model scoring slightly below the strongest one is fine if it clears the bar you set — that gap is what you are being paid for in cost savings. Chasing parity with the reference throws away the target you did the work to establish.

Keep `rejected`. "We tried the small model and it scored 0.81 against a 0.90 target" is the answer to a question that gets asked every quarter, and nobody remembers it accurately.

## The step that makes the ladder work

A small model failing is not automatically evidence you need a bigger one.

**The diagnostic:** if a large model passes and a small model fails *on the same task*, the large model is absorbing ambiguity that exists in your tools, schemas, or instructions. It has enough capacity to infer what you meant. The small model does not, so it surfaces the under-specification as a failure. **That failure is information about your interface, not just about the model.**

```python
INTERFACE_FIXES = [
    ("sharpen_descriptions", sharpen_tool_descriptions),   # cheapest
    ("add_input_examples",   add_input_examples),
    ("decompose_confusing",  decompose_by_failure),
    ("narrow_task",          split_ambiguous_step),
    ("reduce_tool_count",    filter_or_defer_tools),       # most involved
]

def descend_with_fixes(ladder, suite, *, target, reference, tools):
    for rung in ladder:
        if rung.cost_per_task >= reference.cost_per_task:
            break
        result = suite.run(rung.model_id, tools=tools)
        if result.pass_rate >= target:
            return rung.model_id, tools, []

        applied = []
        for name, fix in INTERFACE_FIXES:
            tools = fix(tools, result.failures)       # driven by the actual failures
            applied.append(name)
            result = suite.run(rung.model_id, tools=tools)
            if result.pass_rate >= target:
                return rung.model_id, tools, applied  # saving kept permanently
    return reference.model_id, tools, []
```

Two properties worth noticing:

**The fixes are driven by `result.failures`**, not applied blindly. Many invalid-parameter errors means descriptions or examples; a specific confusion between two tools means decomposition. `tool-design`'s `references/eval-loop.md` has the diagnostic table.

**The improved `tools` propagate.** These fixes remove ambiguity that was costing you on the large model too — you are not trading quality for cost, and if you end up back on the reference model you still keep a better interface.

The order matters because **it is cheaper to fix a tool description than to pay a tier difference on every request forever.** Escalating first hides the ambiguity rather than removing it, and you carry the cost indefinitely.

## When no candidate passes

The case people leave unhandled, and it has three distinct sub-cases.

```python
def analyze_no_pass(rejected, target, reference) -> str:
    best = max(r[1] for r in rejected) if rejected else 0.0
    gap = target - best

    if gap > 0.15:
        return ("capability_gap: the cheapest candidates are far from the target. "
                "The reference model is the answer. Re-check in a quarter.")
    if gap > 0.05:
        return ("near_miss: re-examine the failures. If they cluster on one task "
                "type, split that class out and route only it to the reference "
                "model — the rest may still ride the cheap one.")
    return ("close: check whether the target is right. Re-derive break-even from "
            "unit economics; a target set by intuition may be above what errors "
            "actually cost you.")
```

**`capability_gap`** — the reference model is the answer. That is a real finding, not a defeat: you now know the requirement is capability rather than clarity, and you have a better interface either way. Re-run the ladder when the catalog changes, which is roughly monthly.

**`near_miss`** — the highest-value branch. Look at *which* cases failed. If the failures cluster on one task type, you do not need the expensive model for everything:

```python
def split_by_failure_cluster(failures, candidate, reference):
    hard = {f.task_class for f in failures}
    return {"routes": {cls: (reference if cls in hard else candidate)
                       for cls in ALL_TASK_CLASSES}}
```

Consider splitting the work before concluding the whole system needs one model. Often cheaper than finding one model that does everything — see `routing.md`.

**`close`** — check the target itself. "As accurate as possible" is not a target; derive it from what errors cost. OpenAI's worked example: in a news classification system where a correct classification saves $50 of human review and an incorrect one costs $300 in review and complaint handling, break-even is 85.8%, so target 90%+ to be genuinely positive. If your target was picked by intuition rather than by that arithmetic, it may be above what your errors actually cost.

## Report the full run

```text
Reference: large-model — 0.94 pass, $0.0208/task

Ladder (gated on strict_tools + structured_outputs, ≥32K context):
  small-model   $0.0099   0.81 → rejected
                          + sharpen_descriptions  → 0.86
                          + add_input_examples    → 0.91  ✓ SELECTED
  mid-model     $0.0275   not reached (costlier than reference)

Selected: small-model at 0.91 (target 0.90), saving $0.0109/task (52%)
Interface fixes applied: sharpen_descriptions, add_input_examples
Kept: those fixes also raised large-model to 0.96
```

That last line is the one that turns this from a cost exercise into an engineering one.

## Re-running

The ladder is not a one-time exercise. Re-run when:

- **The catalog changes** — monthly is a reasonable cadence. Re-pull, re-gate, re-rank by cost per task, re-run the suite against anything now cheaper than your pin.
- **The token profile shifts.** Inputs got longer, tool results grew — the cost ordering moves under you.
- **The eval suite changes.** New cases can change which candidates pass.
- **The target changes.** New unit economics, new break-even, possibly a new answer.

```python
def scheduled_review(pin, matrix, profile, suite, target):
    ladder = build_ladder(matrix, profile, MIN_CONTEXT)
    reference = by_id(ladder, pin)
    selection = descend(ladder, suite, target=target, reference=reference)
    if selection.model_id != pin:
        open_pr(f"Switch to {selection.model_id}: {selection.pass_rate:.0%} pass "
                f"(target {target:.0%}), saving {selection.saving_vs_reference:.4f}/task")
```

Open a PR, don't switch automatically. A model change is a code change: pinned ID, eval delta in the description, reviewed and merged like anything else.

## Never do this

**Dynamic cheapest-model routing.** "Whatever is cheapest right now" ships an unevaluated model to production the moment the catalog moves. Pin the ID; review on a schedule.

**Starting development on the cheap model.** You end up unable to tell whether a failure is the model, the prompt, the tools, or an impossible task. Establish the bar on the strongest model first.

**Escalating on the first failure.** Fix the interface first. Escalating buys a permanent per-request cost to hide an ambiguity you could have removed once.

**Assuming a small model fails before testing it.** As unmeasured as assuming it passes. Most production calls are classification, extraction, and formatting — run the suite before paying for a large model on them.
