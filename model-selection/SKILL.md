---
name: model-selection
description: Use when choosing which model to call, when hardcoding a model string in new code, when costs are too high, when someone asks whether a cheaper or smaller model would work, or when routing different request types to different models. Use it against any provider exposing a /models endpoint, and when a system calls one large model for every request regardless of difficulty. Covers capability gating, cost-per-task math, and eval-driven escalation from small models to large.
version: 1.0
---

# Model Selection

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

**Accuracy first, cost second.** Start development on the most capable model available and get the system actually working. Only then find the cheapest model that holds that quality.

This order exists because you cannot optimize toward a bar you haven't established. Starting cheap means you can't tell whether a failure is the model, the prompt, the tools, or a task that no model can do as specified. Starting strong separates those: once the strongest model passes, every later failure is a cost-optimization problem with a known-good reference to compare against.

Two things to never do regardless of phase: **pick a model by price alone** (price says nothing about whether it supports strict tool calling, structured outputs, or your context length), and **route dynamically to whatever is cheapest right now** (you will silently ship an unevaluated model).

## Avoid / Prefer

| Avoid | Prefer |
|---|---|
| Price as the first filter | The capability gate, then cost |
| Cost per token | Cost per successful task |
| Development starting on a cheap model | The strongest model as the reference |
| Escalating on the first failure | Sharper descriptions and examples first |
| Cheapest-right-now routing | A pinned model ID, reviewed on a schedule |
| One model for every request | Routing by request class |
| Assuming a small model will fail | Running the suite on it |

These are defaults, not laws; the rest of this file covers how far below the reference a cheaper model may sit, and when escalation is the honest answer rather than the lazy one.

## Minimal pattern

```text
Set an accuracy target from what an error actually costs
    |
    v
Hit it on the strongest model; pin that as the reference
    |
    v
Gate candidates on supported parameters and context length
    |
    v
Rank the survivors by cost per successful task
    |
    v
Run the unchanged suite on the cheapest; fix the interface before escalating
    |
    v
Pin whichever model still clears the target
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## The two phases

### Phase 1 — Accuracy: make it work on the strongest model

1. **Set an accuracy target** before writing code. Not "good," a number: *90% of support tickets triaged correctly on the first interaction.* See the ROI math below for how to pick it.
2. **Build an evaluation dataset.** A hundred real examples with inputs and correct outputs is plenty to start. For triage: what the user asked, what the system decided, what it should have decided, correct or not.
3. **Use the most capable model available** to hit the target.
4. **Iterate prompts and tools — not the model — until it passes.** This is where tool descriptions, `input_examples`, decomposition, and task scoping get worked out. See `tool-design`.
5. **Pin that as your reference implementation.** It is the ceiling and the thing every cheaper candidate gets compared to.

If the strongest model can't hit the target after honest iteration, stop. No cheaper model will, and the problem is the task definition, the tools, or the target.

### Phase 2 — Cost: find the cheapest model that holds it

6. **List candidates** from the provider's `/models` endpoint.
7. **Gate on capability** — drop anything lacking the parameters your code depends on. Non-negotiable.
8. **Sort survivors by cost per task**, not cost per token.
9. **Run the Phase 1 eval suite** against the cheapest survivor.
10. **On failure, fix the interface first** — descriptions, examples, decomposition, task scope. Re-run.
11. **Escalate one tier only if it still fails** after the interface is clean.
12. **Consider splitting the work.** The whole system may not need one model; route the easy classes down. Often cheaper than finding one model that does everything.
13. **Pin the winner.** Re-run the suite whenever you change it.

The common failure is doing Phase 2 first, which is guessing, or never doing it at all, which is the large-model-for-everything default most codebases land in.

## Setting the accuracy target

"As accurate as possible" isn't a target. Derive it from what errors actually cost.

Work the unit economics: a correct decision saves the cost of a human doing it; an incorrect one triggers rework, escalation, or a complaint. Those two numbers give you a break-even accuracy, and you target comfortably above it.

OpenAI's worked example: in a news classification system where a correct classification saves $50 of human review and an incorrect one costs $300 in review and complaint handling, break-even is 85.8% — so target 90%+ to be genuinely positive.

Two things this gives you that a vague target doesn't: a defensible answer to "is this good enough to ship," and a defensible answer to "is the cheaper model good enough" — since you can price the accuracy drop against the cost saving directly.

One useful side effect of Phase 1: a strong model working well is also a generator of high-quality examples. Capture them — they become few-shot examples and `input_examples` that help the cheaper model in Phase 2.

## Discovery: call /models

```python
import httpx

r = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
models = r.json()["data"]

# Each entry carries:
#   id, name, description, context_length
#   architecture: {input_modalities, output_modalities, tokenizer, instruct_type}
#   pricing: {prompt, completion, ...}  -- USD per token, as strings; "0" means free
#   top_provider, per_request_limits, supported_parameters
```

The list endpoint takes optional `offset` and `limit`; pagination is opt-in, and omitting both returns the full list with `links.next` as null.

For any OpenAI-compatible provider, `GET /v1/models` exists but usually returns only `{id, created, owned_by}`. OpenRouter's is unusually rich — `supported_parameters` in particular is what makes capability gating possible. If your provider returns the bare shape, you must maintain the capability matrix yourself.

## Gate on capability before you look at price

```python
REQUIRED = {"tools", "structured_outputs"}   # whatever your code actually depends on

def usable(m, min_context=32_000):
    params = set(m.get("supported_parameters") or [])
    return REQUIRED <= params and (m.get("context_length") or 0) >= min_context

candidates = [m for m in models if usable(m)]
```

`supported_parameters` reports which OpenAI-compatible parameters actually work for that model — `tools`, `response_format`, `structured_outputs`, `reasoning`, and others. Gate on the ones your code sends.

### The failure this prevents

**OpenRouter will pass `tools` through to providers implementing OpenAI's interface, map them for providers with custom interfaces, and otherwise transform the tools into a YAML template in the prompt.** The model then responds with an assistant message that has to be parsed back out.

That last path is prompt-engineered tool calling wearing the API's clothes. Your request succeeds. You get something tool-shaped back. And you have silently lost every guarantee the `llm-tool-calling` skill is built on: no constrained decoding, no schema enforcement, no protection against invented tool names or malformed arguments.

Nothing in the response says "by the way, this was a YAML template." The only defense is gating on `supported_parameters` before you send.

The same reasoning applies to structured output: a model without `structured_outputs` or `response_format` support cannot give you the conformance guarantee, regardless of what you put in the payload.

## Cost per task, not cost per token

Pricing is per token in USD. To compare models you need per-million figures and, more importantly, **cost per task**.

```python
def per_million(m):
    p = m["pricing"]
    return {
        "in":  float(p["prompt"]) * 1_000_000,
        "out": float(p["completion"]) * 1_000_000,
    }

def cost_per_task(m, avg_in_tokens, avg_out_tokens):
    pm = per_million(m)
    return (avg_in_tokens / 1e6) * pm["in"] + (avg_out_tokens / 1e6) * pm["out"]

ranked = sorted(candidates, key=lambda m: cost_per_task(m, 4_000, 800))
```

Three reasons per-token price misleads:

**Tokenizers differ.** The same text is a different number of tokens across models, and you are billed on the model's own tokenizer. Two models at identical per-token prices can differ materially on the same input.

**Reasoning models emit invisible tokens.** A model that thinks before answering bills those tokens. A "cheaper" reasoning model can cost more per task than a pricier non-reasoning one.

**Retries and failures are part of the cost.** A cheap model that fails your eval 30% of the time and gets retried is not cheap. Measure cost per *successful* task.

Get `avg_in_tokens` and `avg_out_tokens` from your eval harness — it already tracks them if you followed `evals-before-shipping`.

## Descend the ladder

You have a reference implementation passing at a known rate. Now walk down, comparing each candidate against that bar rather than against a guess.

```python
LADDER = ["small-cheap-model", "mid-model", "large-model"]   # gated, cost-sorted
REFERENCE_PASS_RATE = 0.94   # what the strongest model achieved in Phase 1

for model in LADDER:
    results = run_eval_suite(model)          # the Phase 1 suite, unchanged
    if results.pass_rate >= TARGET:
        print(f"Selected {model} at {results.pass_rate:.0%} "
              f"(reference: {REFERENCE_PASS_RATE:.0%})")
        break
else:
    print("No cheaper candidate held the bar — the reference model is the answer")
```

Note the comparison is against `TARGET`, not against the reference. A cheaper model scoring slightly below the strongest one is fine if it still clears the bar you set — that gap is what you are being paid for in cost savings. Chasing parity with the reference wastes the target you did the work to establish.

**What small models are genuinely good at:** classification, routing, extraction against a clear schema, reformatting, short summarization, yes/no judgments, triage. These are the bulk of calls in most production systems.

**Where they tend to fail:** long multi-step reasoning, tool selection across many tools, ambiguous instructions, tasks needing broad world knowledge, and long-context synthesis. Your evals tell you which side your task sits on — the only reliable signal.

## Before escalating, fix the interface

A small model failing your suite is not automatically evidence that you need a bigger one. Escalation is only one of two moves available, and it is the expensive one.

**The diagnostic:** if a large model passes and a small model fails *on the same task*, the large model is absorbing ambiguity that exists in your tools, schemas, or instructions. It has enough capacity to infer what you meant. The small model does not, so it surfaces the under-specification as a failure. That failure is information about your interface, not just about the model.

Make the ambiguity explicit and re-run. In order of cost to try:

1. **Sharpen tool and parameter descriptions.** Write them for a new hire, not a colleague who shares your context. Small models are far less forgiving of implied conventions.
2. **Add `input_examples`** where argument formats or optional-field combinations are non-obvious. This is the cheapest large win for wrong-argument failures.
3. **Decompose tools where the eval shows a specific confusion** — the include/exclude pattern, or any branch the model has to reason about rather than read off the name. Semantics encoded in the name don't have to be inferred.
4. **Narrow the task.** Split one ambiguous step into two unambiguous ones, or move a decision out of the model and into your code.
5. **Reduce the tool count in play** via filtering or `defer_loading`. Selection accuracy degrades fastest on small models, so a catalog a large model handles fine may be past the cliff for a small one.

All of these are in `tool-design`, applied here with the eval failure telling you which one to reach for. They also improve the large model's behavior — you are not trading quality for cost, you are removing ambiguity that was costing you on both.

**Then re-run the suite on the small model.** Frequently it now passes, and you keep the cost saving permanently.

**If it still fails after the interface is clean, the task genuinely needs more capability.** Escalate, and treat that as a real finding rather than a defeat — you now know the requirement is capability rather than clarity, and you have a better interface either way.

The order matters because it is cheaper to fix a tool description than to pay a tier difference on every request forever. Escalating first hides the ambiguity rather than removing it, and you carry the cost indefinitely.

## Route by request class

One model per system is a simplification, not a requirement. Routing easy inputs to a small fast model and hard ones to a capable model is a standard cost-control pattern, and it is just the routing workflow from `agent-vs-workflow-decision` applied to model choice.

```python
def route(request):
    if request.kind in ("classify", "extract", "format"):
        return SMALL
    if request.needs_tools and len(request.tools) > 10:
        return LARGE          # tool selection degrades fastest on small models
    return MID
```

Classify with code where you can. If classification itself needs a model, use the small one — a cheap classifier in front of an expensive generator usually pays for itself.

Two places routing pays especially well:

- **Subagents.** They inherit the parent's model by default. Bounded triage or search work does not need the orchestrator's tier — set `model` explicitly per subagent. See `subagents-and-multi-agent`.
- **LLM judges in evals.** Judge quality matters, but judging a binary assertion does not need your most expensive model. Calibrate a cheaper judge against human labels first.

## Pin the model, and watch for drift

**Pin an explicit model ID in production.** Do not route to "whatever is cheapest right now." The cheapest model changes without warning, and you will be running an unevaluated model in production the moment it does.

Use dynamic `/models` queries for **discovery and periodic review**, not per-request selection. A reasonable cadence: re-pull the catalog monthly, re-gate, re-rank by cost per task, and re-run the eval suite against anything now cheaper than your current pin. Switch only if it passes.

If you use a provider's automatic router or fallback chain, know which models it can reach and confirm every one of them clears your capability gate. A fallback to a model without `tools` support is the YAML-template failure again, triggered by an outage rather than a config error.

Model IDs also carry provider and quantization differences behind one name. Where the provider exposes per-endpoint detail — definitive supported parameters and pricing per serving endpoint — check it before assuming a model ID behaves identically everywhere.

## Pitfalls

**Selecting on price before capability.** The gate is not a preference. A cheaper model that can't do strict tool calling is not a cheaper option, it's a broken one.

**Trusting that a request succeeded.** Tool calls come back from models that don't support tool calling, via prompt templating. Success is not evidence of capability.

**Comparing per-token prices across tokenizers.** Compare cost per task on your actual traffic.

**Ignoring reasoning tokens.** They bill, and they don't appear in the answer.

**Not counting retries.** Cost per successful task is the number that matters.

**Dynamic cheapest-model routing in production.** Pin it. Review on a schedule.

**Starting development on a cheap model.** You end up unable to tell whether a failure is the model, the prompt, the tools, or an impossible task. Establish the bar on the strongest model first, then descend with a reference to compare against.

**Escalating on the first failure.** A small model failing is a signal about your interface as often as about the model. Sharpen descriptions, add examples, decompose the confusing tool, then re-run. Escalating first buys a permanent per-request cost to hide an ambiguity you could have removed once.

**Assuming a small model fails before testing it.** This is as unmeasured as assuming it will pass. Most production calls are classification, extraction, and formatting — run the suite before paying for a large model on those.

**One model for everything.** Route by request class. The difference is usually large and almost free to implement.

## Success criteria

Model selection is the one decision in this repo with a number attached by construction. Check that the number moved in the direction you claimed:

- **Pass rate on the unchanged Phase 1 suite** for the pinned model, reported against both the target and the reference model's rate — re-run on every pin change, which is what `evals-before-shipping/references/ci-integration.md` is for
- **Cost per successful task**, with retries and reasoning tokens counted, not per-token price
- **Share of traffic served by the cheaper tier** without a pass-rate drop, which is the payoff from routing
- **Requests sent to a model lacking a parameter your code depends on** — this should be zero, including through fallback chains
- **Tool-selection accuracy on the small model specifically**, because that is where it degrades first: `evals-before-shipping/references/tool-call-suite.md`
- **p50 and p95 latency per request class** after routing, since the small tier is usually bought for both
- **Eval failures fixed by sharpening the interface rather than escalating** — a high count means ambiguity was being paid for per request

If none of these move, the pin you changed to did not help on that task; revert to the reference and keep the interface improvements, which are free. A cost saving you cannot show alongside an unchanged pass rate is not a saving.

## References

- `references/openrouter-models.md` — full `/models` response shape, filtering, per-endpoint detail, pagination
- `references/capability-matrix.md` — building and maintaining a matrix for providers with a bare `/models` endpoint
- `references/cost-modeling.md` — cost per successful task, reasoning-token accounting, retry overhead
- `references/routing.md` — request classifiers, fallback chains that respect the capability gate
- `references/escalation-ladder.md` — wiring the ladder into the eval harness, including the no-candidate-passes case