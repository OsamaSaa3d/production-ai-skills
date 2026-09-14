# Routing by Request Class

One model per system is a simplification, not a requirement. Routing is the routing workflow from `agent-vs-workflow-decision` applied to model choice, and it is usually the largest cost win available that costs nothing in quality — because most production traffic is classification, extraction, and formatting, which small models handle well.

## Classify with code first

The cheapest classifier is the one that is not a model call.

```python
def route(request) -> str:
    # 1. structural facts you already have
    if request.kind in ("classify", "extract", "format", "translate"):
        return SMALL
    if request.needs_tools and len(request.tools) > 10:
        return LARGE            # tool selection degrades fastest on small models
    if request.input_tokens > 100_000:
        return LARGE            # long-context synthesis
    if request.requires_multi_step_reasoning:
        return LARGE
    return MID
```

Most systems know more than they think at dispatch time: the endpoint that was hit, the document type, the user's plan tier, the length of the input, whether tools are in play. All of that is free.

Only when code genuinely cannot decide do you spend a model call — and then use the small model for it. **A cheap classifier in front of an expensive generator usually pays for itself.**

```python
class Difficulty(BaseModel):
    reasoning: str
    level: Literal["simple", "moderate", "complex"]

def classify_difficulty(request) -> str:
    result = call(SYSTEM_TRIAGE, request.text, schema=Difficulty, model=SMALL)
    return {"simple": SMALL, "moderate": MID, "complex": LARGE}[result.level]
```

Note `reasoning` before `level` — fields generate in order, so a reasoning field declared first is thinking rather than rationalization. See `structured-output`.

## What small models are genuinely good at

| Good | Tends to fail |
|---|---|
| Classification, routing, triage | Long multi-step reasoning |
| Extraction against a clear schema | Tool selection across many tools |
| Reformatting, translation | Ambiguous instructions |
| Short summarization | Broad world knowledge |
| Yes/no judgments | Long-context synthesis |

These are not predictions. **Your evals tell you which side your task sits on** — that is the only reliable signal, and assuming a small model will fail is exactly as unmeasured as assuming it will pass.

## Every route needs its own eval

This is the rule that makes routing safe. A route is a model running in production, and an unevaluated route is an unevaluated model in production.

```python
ROUTES = {
    "classify": {"model": SMALL, "suite": "tests/evals/classify.py",  "target": 0.92},
    "extract":  {"model": SMALL, "suite": "tests/evals/extract.py",   "target": 0.90},
    "reason":   {"model": LARGE, "suite": "tests/evals/reason.py",    "target": 0.88},
}
```

Run each route's suite against its pinned model in CI. Changing a route's model is a code change requiring a full re-run of that route's suite, in the same PR.

## Evaluate the router itself

The router is a component that fails, and its failures are asymmetric.

```python
ROUTER_CASES = [
    {"input": "Categorize this ticket: 'card declined'", "expected": SMALL},
    {"input": "Compare these three contracts and flag conflicting clauses",
     "expected": LARGE},
    {"input": "What's the status of order 4471?", "expected": SMALL},
]
```

| Misroute | Cost |
|---|---|
| Hard task → small model | A wrong answer. Expensive, possibly invisible. |
| Easy task → large model | A few cents. Invisible, harmless. |

**Bias the router toward over-routing.** When the classifier is uncertain, send it up. The downside is a rounding error; the downside of the other direction is a wrong answer delivered confidently.

Build the router's ambiguous cases from production misroutes — they are the only source of genuinely hard examples.

## Fallback chains must respect the gate

A fallback triggered by an outage is a model change made under pressure by infrastructure. It must clear the same capability gate as a deliberate one.

```python
FALLBACK = {
    LARGE: [LARGE_ALT, MID],
    MID:   [MID_ALT, LARGE],       # falling UP is fine — it costs more, not less
    SMALL: [SMALL_ALT, MID],
}

def call_with_fallback(request, model, *, max_attempts=3):
    chain = [model, *FALLBACK.get(model, [])][:max_attempts]
    last = None
    for candidate in chain:
        assert usable(CAPS[candidate]), f"{candidate} fails the capability gate"
        try:
            return call(request, model=candidate)
        except (RateLimitError, APIStatusError, APIConnectionError) as e:
            log.warning("fallback", frm=candidate, err=type(e).__name__)
            last = e
    raise last
```

Three rules:

**Assert the gate on every chain member, in CI.** A fallback to a model without strict tool support is prompt-templated tool calling — no constrained decoding, no schema enforcement — triggered at the worst possible moment with nothing in your logs saying so.

**Fall back to a model you have evaluated on that route.** An unevaluated fallback is an unevaluated model in production, and it is running precisely when you are least able to notice.

**Log every fallback.** A silent fallback that fires on 8% of traffic is a quality regression nobody can see. Alert on the rate.

Falling *up* the tier is a legitimate chain: it costs more and it works.

Anthropic's server-side fallbacks are a different mechanism worth knowing where applicable — `betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"` routes by refusal category without you maintaining a chain at all.

## Prompts are per-route too

A prompt is validated against the model it was measured on. A route sending the same prompt to a small model and a large one is validated on neither.

When a route uses a cheaper model, the scaffolding usually has to come back: more explicit tool descriptions, more examples, narrower tasks. That is the prompt-side view of "fix the interface before escalating" — the same work, arrived at from the other direction. See `system-prompt-engineering`.

```python
PROMPTS = {
    (SMALL, "extract"): PROMPT_EXTRACT_EXPLICIT,     # more scaffolding
    (LARGE, "extract"): PROMPT_EXTRACT_TERSE,
}
```

## Caches are model-scoped

A cascade forfeits cache reuse across its models. Each model has its own cache namespace, so splitting traffic between two models splits your cache and lowers the hit rate on both.

This is a real cost that cascade proposals rarely account for, and it argues for **measuring the simpler alternative first**: the capable model at lower effort, on the same tasks. Lower effort on a newer model often matches or exceeds a prior generation at high effort, and one model means one cache namespace.

## What to log

```python
{"request_id": ..., "route": "extract", "model_selected": SMALL,
 "router_method": "code" | "classifier", "classifier_confidence": "high",
 "fell_back_from": None, "cost_usd": 0.0031, "cache_read_tokens": 3_010,
 "passed_validation": True}
```

`route` plus `model_selected` makes cost-per-class a query. `fell_back_from` surfaces silent degradation. `router_method` tells you whether the classifier is earning its call — if 95% of decisions are made in code, the model classifier is overhead on the remaining 5%.

## Pitfalls

**Routing before establishing the bar.** Get the system working on the strongest model first. Otherwise a route failure is indistinguishable from a prompt, tool, or task-definition failure.

**Routes without evals.** Every route is a model in production.

**A router nobody evaluates.** It is a classifier and it misclassifies.

**Under-routing on uncertainty.** Bias up. The asymmetry is large.

**Dynamic cheapest-model routing.** Pin every route to an explicit model ID. Review the catalog monthly; switch only on a passing eval run.

**Ignoring the cache split.** Two models means two cache namespaces and a lower hit rate on both. Price that in before you split.
