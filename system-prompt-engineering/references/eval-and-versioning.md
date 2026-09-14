# Prompt Evals and Versioning

## Treat the prompt as application code

Prompts are behavior. Manage them the way you manage behavior. Prefer code-managed prompt modules over provider-hosted prompt objects — OpenAI is deprecating reusable prompt objects specifically in favor of this pattern.

```text
prompts/
  support_reply.py        # the prompt text, as a module-level constant
  support_reply_test.py   # the regression suite for it
  triage.py
  triage_test.py
```

Rules:

- **Text lives in a named module**, not inline in a request handler.
- **Dynamic sections come from typed parameters or validated input objects**, not `.format()` on a blob. This is what makes the cache-safety invariants enforceable and reviewable.
- **Prompt changes ship in the same PR as the behavior they support**, with the eval delta in the description.
- **Version control, PR review, release tags, and feature flags** are the review/ship/compare/rollback mechanism. You don't need a prompt platform for this.

```python
# prompts/support_reply.py
from dataclasses import dataclass

SYSTEM = """..."""          # static; goes in `system`, cached

@dataclass(frozen=True)
class RequestContext:
    today: str
    customer_tier: str

def render_context(ctx: RequestContext) -> str:
    """Dynamic content. Goes in `messages`, after the cache breakpoint."""
    return f"<request_context>\ndate: {ctx.today}\ntier: {ctx.customer_tier}\n</request_context>"
```

The type signature is the documentation of what varies per request — and the thing a reviewer can check against the caching rules.

## The regression suite

Every prompt change runs against a fixed case set. Structure each case around the failure it was written for.

```python
CASES = [
    {
        "id": "tool_eagerness_conceptual_question",
        "input": "How do I make an offsite more sustainable in general?",
        "asserts": [
            no_tool_calls,
            max_words(120),
        ],
        # why this case exists — so a future reader can delete it safely
        "origin": "2026-02 failure batch: conceptual questions triggered venue_search",
    },
    {
        "id": "persistence_multi_file_change",
        "input": "Rename the fib function everywhere and update the tests.",
        "asserts": [
            touched_files_at_least(2),
            no_handback_before_completion,
        ],
        "origin": "2026-03: agent stopped after analysis",
    },
]
```

Three properties that make this suite useful rather than decorative:

**Every case names its origin.** A case with no recorded reason cannot be deleted responsibly, and suites that can't be pruned stop being run.

**Assertions are mostly deterministic.** Tool-call presence, tool names and arguments, length, schema conformance, and forbidden-substring checks are cheap and stable. Reach for an LLM judge only for genuinely subjective properties — tone, helpfulness — and calibrate it against human labels first. See `evals-before-shipping`.

**Every promoted instruction has a case.** If adding a rule doesn't come with a case that fails without it, you cannot later tell whether the rule is still needed. That is how prompts become graveyards.

## A/B-ing two prompt versions

Same cases, same model, same seed where available, both variants:

```python
def compare(variant_a, variant_b, cases):
    rows = []
    for case in cases:
        a = run(variant_a, case)
        b = run(variant_b, case)
        rows.append({
            "id": case["id"],
            "a_pass": a.passed, "b_pass": b.passed,
            "a_tokens": a.total_tokens, "b_tokens": b.total_tokens,
            "a_tool_calls": len(a.tool_calls), "b_tool_calls": len(b.tool_calls),
        })
    return rows
```

Report per-case, not just aggregate. A change that lifts the pass rate 4 points while breaking two previously-passing cases is a different decision than a clean 4-point lift, and the aggregate hides it.

Track alongside accuracy: **tokens per task, tool calls per task, and cache hit rate.** A prompt that improves accuracy by 2% while doubling tokens and killing the cache may be a net loss.

## CI

```text
on: pull_request touching prompts/**
  - run the regression suite on the pinned model
  - fail on any newly-failing case
  - fail if the cacheable prefix is not byte-stable across differing request context
  - post the per-case diff and the token/cache deltas as a comment
```

The prefix-stability test is cheap and catches an entire class of expensive mistake:

```python
def test_prefix_is_stable():
    a = render_prefix(RequestContext(today="2026-01-01", customer_tier="free"))
    b = render_prefix(RequestContext(today="2026-06-01", customer_tier="enterprise"))
    assert a == b, "dynamic content leaked into the cacheable prefix"
```

## Pin the model and the prompt together

A prompt is only validated against the model it was measured on. Record both, and treat a model change as a prompt change requiring a full re-run.

```python
CONFIG = {
    "model": "claude-opus-5",          # pinned, not an alias
    "prompt_version": "support_reply@2026-03-14",
    "reasoning_effort": "medium",
    "verbosity": "low",
}
```

Prefer a dated model ID over a moving alias for anything you regression-test against. An alias that silently advances turns your suite into a source of unreproducible failures.

## The model-change audit

Run it in **both** directions. This is the step almost nobody does.

**On upgrade**, look for scaffolding around a capability gap that has since closed:

- Rules that are now judgment calls the model makes correctly on its own. Delete them and confirm the eval holds.
- Instructions duplicated between the system prompt and a tool description. Keep the tool description.
- Formatting-suppression blocks. A newer model may already format less than the block assumes, in which case the block suppresses structure the content needs.
- Emphasis hacks — all-caps, bribes, threats. Strongly instruction-following models may over-weight them.
- Few-shot examples that only existed to teach a format the model now produces natively.

**On downgrade** — routing a step to a cheaper model to cut cost — the same audit runs in reverse. You have reduced the judgment you can assume, so some scaffolding needs to come back: more explicit descriptions, more examples, narrower tasks. This is the prompt-side view of `model-selection`'s "fix the interface before escalating."

Procedure either way:

```text
1. Run the current prompt on the new model. Record the per-case delta.
2. For each newly-failing case, add the minimum instruction that fixes it.
3. For each rule you suspect is obsolete, delete it and re-run. Keep the
   deletion only if nothing regresses.
4. Re-check the cache prefix and the token/latency profile — effort and
   verbosity defaults differ between models.
5. Commit the prompt, the model pin, and the eval delta as one change.
```

Step 3 is the one that keeps prompts from growing monotonically forever. Schedule it even without a model change — quarterly is reasonable.

## Instruction density: measure your own position

"Models can't follow many rules" used to be a reason to keep prompts tight. It is no longer a good one, and the correction is worth knowing precisely because it changes what you should be measuring.

The IFScale benchmark (2025) packed up to 500 simultaneous instructions into one prompt and found the best frontier model of the day managed **68% adherence at 500**. A 2026 replication found that headline had moved by roughly an order of magnitude — current frontier models hold near-perfect adherence into the thousands of constraints, and the ceiling had to be pushed past 5,000 before meaningful degradation appeared.

What survives as a reason to keep a prompt tight:

- The attention budget is finite and context rot is real across all models.
- Every token is billed on every request, forever.
- The odds that rule 60 conflicts with rule 12 rise faster than either author notices — and a contradiction presents as unreliability, not as a contradiction.
- Rules encode capability gaps, and gaps close. An unpruned prompt accumulates dead scaffolding.
- **Your position on the degradation curve is unknown until you measure it.**

That last one is the operational point, and it belongs to your eval suite rather than to a rule of thumb. Measure it directly:

```text
- [ ] Take the prompt's own instruction list as the checklist.
- [ ] Run the regression suite and score per-instruction adherence, not just task success.
- [ ] Record the count of active instructions alongside the score, per run.
- [ ] Re-run on every model change, including downgrades.
```

The count matters because the curve moves under you. Routing a step to a cheaper model to save money can put you somewhere different on it, and a prompt validated at 40 instructions on a frontier model is not validated at 40 instructions on the small one you just switched to.

Order matters somewhat — earlier instructions are better satisfied at moderate densities, and the effect diminishes at extreme densities where failure becomes uniform — but treat that as a tiebreak, not a strategy.

## Metrics worth a dashboard

| Metric | Watch for |
|---|---|
| Pass rate per case group | A group degrading while the aggregate holds |
| Tokens per task | Silent growth from prompt additions |
| Tool calls per task | Eagerness creeping up after an instruction change |
| Cache hit rate | Any drop toward zero — usually a serialization change |
| Turns to resolution | Regressions that don't show up as failures |
| Human-override rate in production | The only metric your suite can't fake |
