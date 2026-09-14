# The Multi-Turn Tool Loop

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

The single-turn example in the skill is the loop with `max_iterations=1`. This is the general form. It is about forty lines, and no framework does anything meaningfully different.

This file covers the *mechanics*. For whether you should be running a loop at all rather than a fixed pipeline, see `agent-vs-workflow-decision`.

## The loop

```python
import json
from dataclasses import dataclass, field

MAX_ITERATIONS = 10

@dataclass
class RunResult:
    text: str | None
    stop: str                      # "done" | "max_iterations" | "budget" | "refusal"
    iterations: int
    tool_calls: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)

def run(user_message: str, tools, registry, max_iterations=MAX_ITERATIONS) -> RunResult:
    messages = [{"role": "user", "content": user_message}]
    calls, usage = [], {"in": 0, "out": 0}

    for i in range(1, max_iterations + 1):
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools, tool_choice="auto",
        )
        usage["in"] += response.usage.prompt_tokens
        usage["out"] += response.usage.completion_tokens

        choice = response.choices[0]
        messages.append(choice.message)          # verbatim, before anything else

        if choice.finish_reason == "length":
            raise RuntimeError(f"truncated on iteration {i}; raise max_completion_tokens")

        if not choice.message.tool_calls:
            return RunResult(choice.message.content, "done", i, calls, usage)

        for tc in choice.message.tool_calls:
            calls.append(tc.function.name)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(execute(tc, registry)),
            })

    return RunResult(None, "max_iterations", max_iterations, calls, usage)


def execute(tool_call, registry) -> dict:
    name = tool_call.function.name
    if name not in registry:
        # the model invented a tool; tell it so rather than raising
        return {"error": f"No tool named {name!r}. Available: {sorted(registry)}"}
    try:
        args = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as e:
        return {"error": f"Arguments were not valid JSON: {e}"}
    try:
        return {"result": registry[name](**args)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
```

Everything important is in the small decisions:

**Append the assistant message before executing anything.** If a tool raises and you unwind, the transcript still has to be coherent for the retry.

**Hitting the iteration cap is a return value, not an exception.** The caller decides whether a partial run is useful. Raising there loses the transcript, the token count, and the tool history — the three things you need to debug it.

**Tool errors are data.** Unknown tool name, unparseable arguments, and a raised exception all become tool results the model can read and react to. The only thing that should escape the loop is a failure the model cannot possibly recover from.

**Track usage as you go.** Per-run token cost is the number you need for `model-selection` and for any budget cap, and you cannot reconstruct it afterward.

## Stopping conditions

An iteration cap alone is the minimum, and it is not enough for anything unattended. Four conditions, in the order they tend to matter:

```python
class Stop(Exception): ...

def check(state):
    if state.iterations >= MAX_ITERATIONS:
        raise Stop("max_iterations")
    if state.cost_usd >= MAX_COST_USD:
        raise Stop("budget")
    if state.elapsed_s >= MAX_WALL_CLOCK_S:
        raise Stop("timeout")
    if state.repeated_identical_calls >= 3:
        raise Stop("stuck")
```

The last one catches the most common real failure: the model calls the same tool with the same arguments, gets the same result, and does it again. Hash `(name, arguments)` per iteration and count repeats.

```python
signature = (tc.function.name, tc.function.arguments)
state.seen[signature] += 1
if state.seen[signature] >= 3:
    # break the cycle in-band before you kill the run
    result = {"error": "You have already called this tool with these exact arguments "
                       "twice and received the same result. Try different arguments "
                       "or answer with what you have."}
```

Telling the model it is looping frequently unsticks it. Do that first; kill the run only if it doesn't work.

## Where to put the budget cap

Cost, not iterations, is what actually hurts. Iterations are a poor proxy — one call with 80K tokens of context costs more than six small ones.

```python
cost = (usage["in"] / 1e6) * PRICE_IN + (usage["out"] / 1e6) * PRICE_OUT
```

Check it *after* each response and *before* the next request. A cap checked only at the top of the loop lets one expensive iteration blow through it.

For a per-run ceiling the model itself can pace against, Anthropic's task budgets pass a token allowance in `output_config.task_budget` and inject a countdown the model can see, so it winds down gracefully instead of being cut off. That is a different mechanism from `max_tokens`, which is an enforced per-response cap the model knows nothing about.

## Context growth

Every iteration re-sends the whole transcript. A ten-iteration run with large tool results can spend most of its budget re-reading its own history.

Three mitigations, cheapest first:

1. **Return less.** A tool that returns 200 rows when the model needs 5 is the actual bug. See `tool-design`.
2. **Truncate old tool results in place** — keep the last N verbatim, replace older ones with a one-line summary. Note that this invalidates the prompt cache from the edit point onward, so truncate in batches rather than every turn.
3. **Clear or compact server-side.** Anthropic's context editing clears old tool results (`clear_tool_uses_20250919`) and thinking blocks; compaction summarizes instead. Both are provider features that spare you writing this logic.

See `context-and-memory` for the full treatment.

## Streaming a loop

Streaming inside a tool loop only helps the final turn — the intermediate turns end in tool calls nobody is reading. A reasonable pattern: run intermediate iterations non-streaming, and stream only once the model returns no tool calls. If you want live progress in the meantime, emit your own events as each tool starts and finishes; that is more legible to a user than raw token deltas anyway.

## What not to add

**A planning step that plans and then ignores the plan.** If you want a plan, make the plan a tool call whose output is in the transcript, so deviation is visible.

**A reflection pass on every iteration.** It doubles cost. Add it after measuring that the loop actually fails in a way reflection fixes.

**A framework, for this.** The whole mechanism is above. What you would be buying is a fixed control flow, error handling that converts exceptions into prompt text, and an upgrade treadmill. See `why-not-frameworks.md`.
