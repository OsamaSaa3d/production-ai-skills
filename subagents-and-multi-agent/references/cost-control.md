# Cost Control for Subagents

Claude decides on its own when to spawn subagents and how many. Subagents can spawn subagents. One prompt can become a tree, and more capable models delegate more readily — so these limits matter *more* as you move up the model tier, not less.

## The three caps

Set all three before running anything unattended.

```python
async for message in query(
    prompt="Audit every service in this repo for unhandled promise rejections",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],
        env={
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "5",
        },
        max_budget_usd=5.0,
    ),
):
    if isinstance(message, ResultMessage):
        print(f"{message.subtype}: ${message.total_cost_usd}")
```

| Limit | Default | Behavior at the limit |
|---|---|---|
| `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | 3 layers | The bottom-layer subagent does the work itself instead of delegating |
| `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | 20 | Returns `Concurrent subagent limit reached` until the count drops |
| `max_budget_usd` / `maxBudgetUsd` | none | Refuses new subagents, stops background ones, ends with `error_max_budget_usd` |

**Subagent requests count toward `total_cost_usd`, so the budget cap is the only hard stop.** Depth and concurrency shape the tree; only the budget bounds the bill.

Depth 1 is the right default. Depth 3 means a single delegation can become a tree whose width is concurrency-limited but whose total is not, and the runs that do this are exactly the ones nobody is watching.

**SDK difference on `env`:** TypeScript *replaces* the subprocess environment — spread `process.env` or you lose `PATH`. Python *merges* into it.

## Model tiering

Subagents inherit the parent's model by default. A triage subagent left on the default costs the same per token as the orchestrator, for work that does not need it.

```python
agents={
    "triage":  AgentDefinition(..., model="haiku"),    # classify, rank
    "explore": AgentDefinition(..., model="sonnet"),   # search, summarize
    "audit":   AgentDefinition(..., model="sonnet"),   # judgment, but bounded
    # the parent keeps the strongest model — it holds the plan
}
```

The rule from `model-selection` applies unchanged: establish quality on the strongest model, then descend per subagent, re-running the eval. A subagent is an unusually good candidate for a cheap model because its task is bounded and its output format is specified — which is exactly the shape small models handle well.

Where they still fail: tool selection across many tools, ambiguous instructions, and long-context synthesis. A subagent doing any of those stays on the bigger model.

## The metric that decides everything: compression ratio

```python
compression = input_tokens_consumed_by_subagent / output_tokens_returned_to_parent
```

This is the number that says whether a subagent is worth its instance cost.

| Ratio | Reading |
|---|---|
| > 20x | Excellent. This is what subagents are for. |
| 5–20x | Worth it. |
| 2–5x | Marginal. Check whether the parent could just do it. |
| < 2x | You are paying for an extra instance to move data. Delete it. |

Measure it per subagent, in production:

```python
{"subagent": "explore", "input_tokens": 41_200, "output_tokens": 380,
 "compression": 108, "cost_usd": 0.14, "elapsed_s": 19}
```

A subagent trending down on compression is usually one whose return format loosened — someone removed "never paste file bodies" from the prompt, or the task grew a "and explain your reasoning" clause. Tighten the return format, not the model.

## Where the tokens actually go

Four line items, in the order they tend to dominate:

**Oversized tool results.** A subagent whose search tool returns 200 rows pays for 200 rows on every subsequent turn of its own loop. This is nearly always the largest item, and it is a tool-design bug rather than an architecture one. Fix it in `tool-design` before touching anything here.

**Re-passed context within a subagent's loop.** Every iteration re-sends that subagent's whole transcript. A subagent with a 10-iteration loop and large results is quadratic in the same way the parent is.

**Duplicate work across subagents.** Two subagents given overlapping objectives run overlapping searches. Log tool calls per subagent and look for the same call in two of them — the fix is in the delegation prompts, not the caps.

**Coordination.** The parent's delegation decisions and its reading of returns produce no task output. Short tasks are mostly this, which is the argument for not delegating trivial work at all.

## A budget that degrades rather than dies

A hard stop mid-run wastes everything spent so far. Better to reserve for synthesis:

```python
@dataclass
class RunBudget:
    total_usd: float = 5.00
    reserve_for_synthesis: float = 0.50

    def remaining_for_workers(self, spent: float) -> float:
        return max(0.0, self.total_usd - self.reserve_for_synthesis - spent)
```

When workers have consumed their share, stop spawning and synthesize from what you have — with the gaps named explicitly. A partial answer that says what is missing beats an `error_max_budget_usd` with nothing to show.

## Preventing the runaway

Three things worth having beyond the caps:

**A per-subagent turn cap.** A subagent that cannot find what it is looking for will keep looking. Bound it in the prompt ("if you have not found it after searching these three locations, report what you searched") *and* structurally where the SDK allows.

**Timeouts.** Cost caps do not stop a subagent blocked on a slow tool. Wall-clock is a separate failure mode and needs a separate limit.

**A kill switch you have tested.** Verify that hitting `max_budget_usd` actually stops in-flight subagents, on your setup, before you rely on it. A cap you have never seen fire is a hypothesis.

## Deciding not to delegate

The cheapest subagent is the one you did not spawn. Before adding one, check the parent cannot be fixed instead:

- **Tool definitions eating context** → deferred loading and tool search. ~72K tokens of definitions down to ~8.7K total in Anthropic's figures, with accuracy improving. See `tool-design`.
- **Tool results eating context** → programmatic tool calling keeps intermediates in a sandbox; ~37% token reduction on complex research tasks.
- **Domain instructions** → a skill. Loads into the parent's context, no extra instance, no delegation round-trip.

Splitting to solve a tool-count problem that a flag already solves buys coordination failure modes for nothing. That is the most common unnecessary subagent.
