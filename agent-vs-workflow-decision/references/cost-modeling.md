# Estimating Cost Per Architecture Before You Build

The purpose of this file is to let you kill an architecture on a whiteboard instead of after the first invoice. Multi-step cost is an architecture problem, not a pricing problem: context gets re-passed and re-billed at every step, retries redo work, and coordination burns tokens producing nothing.

For per-model, per-task cost accounting once you *have* a system, see `model-selection`'s `references/cost-modeling.md`. This one is about choosing the shape.

## The multipliers

Relative to one well-constructed single call, on the same task:

| Architecture | Multiplier | Where it goes |
|---|---|---|
| Single call | 1x | — |
| Augmented call (tools, retrieval) | 1.5–3x | Tool definitions, retrieved context, one or two tool round-trips |
| Workflow, 3 steps | 3–5x | Each step re-sends what it needs |
| Agent | ~15x a single call | Accumulating transcript, re-billed every iteration |
| Multi-agent | ~15x a *chat interaction* | Per-worker context, plus planning and synthesis |

Anthropic's published figures anchor the bottom two rows: agents run roughly 4x the tokens of a chat interaction, multi-agent systems roughly 15x, with token usage explaining most of the performance variance in their research eval.

Use these to reject ideas early. If a single call costs $0.004 and the task is worth $0.02, the multi-agent version is dead before you open an editor.

## The quadratic term nobody budgets

The agent multiplier is not linear in iterations. Every iteration re-sends the entire transcript.

```python
def agent_tokens(system, per_tool_result, iterations):
    """Input tokens billed across the whole run."""
    total, context = 0, system
    for _ in range(iterations):
        total += context                 # the whole transcript, again
        context += per_tool_result + 200 # result plus the model's own turn
    return total
```

| Iterations | Tool result size | Input tokens billed |
|---|---|---|
| 5 | 500 | ~19,000 |
| 5 | 5,000 | ~68,000 |
| 15 | 500 | ~72,000 |
| 15 | 5,000 | ~633,000 |

Two readings, both important:

**Tool result size dominates.** A 10x larger tool result costs roughly 9x more over a 15-iteration run — far more than the same factor on a single call. The cheapest optimization in any agent is nearly always making tools return less. See `tool-design`.

**Iteration count compounds.** Doubling the cap more than doubles the bill. A cap of 15 is not "three times a cap of 5."

Prompt caching flattens the curve substantially — the stable prefix is re-read at a discount — but only if your prefix is actually stable. A transcript that grows at the end and never changes at the front caches well; one where you edit or truncate old tool results does not.

## Estimating before you build

Five numbers, all of which you can get in an afternoon:

```python
SYSTEM_TOKENS      = 800      # count it, don't guess: use the provider's token counter
TOOL_DEFS_TOKENS   = 1_200    # charged on every request, before any work
AVG_TOOL_RESULT    = 900      # the one people underestimate by 5x
AVG_ITERATIONS     = 6        # from a prototype run on 20 real tasks
OUTPUT_PER_TURN    = 250
```

`AVG_TOOL_RESULT` is where estimates go wrong. Measure it against real data, not a hand-written fixture — a search tool returning three tidy rows in your test returns eighty in production.

`AVG_ITERATIONS` requires a prototype, which is fine: build the crude version, run twenty real tasks, and count. That prototype also tells you whether an agent is warranted at all.

```python
def estimate(model, iterations=AVG_ITERATIONS, tasks_per_day=1_000):
    inp = agent_tokens(SYSTEM_TOKENS + TOOL_DEFS_TOKENS, AVG_TOOL_RESULT, iterations)
    out = OUTPUT_PER_TURN * iterations
    per_task = (inp / 1e6) * model.price_in + (out / 1e6) * model.price_out
    return {"per_task": per_task, "per_day": per_task * tasks_per_day,
            "per_month": per_task * tasks_per_day * 30}
```

Then apply the corrections below, because the raw number is optimistic.

## The four corrections

**Retries and failures.** Cost per *successful* task is the only number that matters. A model that fails 20% of the time and gets retried costs 1.25x its sticker price, and the failed run is usually a full-length run.

```python
per_successful_task = per_task / pass_rate
```

**Reasoning tokens.** Models that think before answering bill those tokens, and they do not appear in the response. A "cheaper" reasoning model can cost more per task than a pricier non-reasoning one. Read `usage` rather than counting characters in the answer.

**Cache reads.** If your prefix is stable, much of the input bills at the cached rate. This can be a large discount and it is worth modeling explicitly — but verify with the provider's cache-hit field rather than assuming. A single moving token at the front (a timestamp, an unsorted dict) takes the hit rate to zero silently.

**The long tail.** Averages hide the runs that hit the iteration cap. Model the p95, not just the mean: if 5% of runs cost 4x the average, that is 20% of your bill.

## Cheaper before simpler

Before dropping a rung on the ladder, try the levers that cost nothing in capability:

1. **Make tool results smaller.** Pagination, filtering, field selection, `response_format: "concise"`. Biggest lever by a wide margin, and it usually improves accuracy too.
2. **Stabilize the prefix and cache it.** Tools and system prompt first, volatile content last.
3. **Defer tool definitions.** ~72K tokens of definitions down to ~8.7K total context consumption in Anthropic's reported figures, with accuracy improving rather than degrading.
4. **Keep intermediate results out of context.** Programmatic tool calling processes them in a sandbox — reported average token usage of 43,588 → 27,297 (37% reduction) on complex research tasks. Note it costs *more* on sequential single-call workflows (~8% on τ²-bench), so check your workflow shape first.
5. **Lower the iteration cap** and measure what it costs in pass rate. Often nothing.
6. **Route by difficulty.** Easy inputs to a small model. See `model-selection`.

Only after those: drop a rung. Collapse multi-agent to orchestrator-workers, or an agent to a workflow.

## The ROI gate

An architecture is justified when the value of the output clears the cost, not when it is impressive.

```text
value_per_task     = (human_minutes_saved × loaded_rate) + (error_cost_avoided)
cost_per_task      = model_cost + retry_overhead + oversight_cost
```

`oversight_cost` is the one that gets left out and frequently dominates. An agent whose output a human reviews for three minutes has a three-minute cost per task regardless of what the tokens cost. This is often the real argument for a workflow: not that the agent is more expensive in tokens, but that its output needs more checking.

If the value does not clear the cost, the architecture is wrong regardless of how well it works. That is a legitimate and common conclusion.

## Log this from day one

```python
{"run_id": ..., "architecture": "agent", "model": ..., "status": "done",
 "iterations": 7, "input_tokens": 84_120, "cached_read_tokens": 61_000,
 "output_tokens": 1_890, "cost_usd": 0.31, "elapsed_s": 24.1,
 "tool_calls": [{"name": "search_logs", "result_tokens": 4_210}, ...]}
```

`result_tokens` per tool call is the field people omit and then need. It names the specific tool eating your budget, which is nearly always the first thing worth fixing — and it turns the cost conversation from "agents are expensive" into "this one tool returns 4,000 tokens and needs a filter."
