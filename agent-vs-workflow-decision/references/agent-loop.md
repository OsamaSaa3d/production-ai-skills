# A Minimal Agent Loop You Can Defend

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

You have decided the steps are genuinely unknowable and the environment gives real feedback. This is what the loop needs before it runs unattended.

For the tool-calling mechanics — message accumulation, parallel calls, tool errors — see `llm-tool-calling`'s `references/agent-loop.md`. This file covers the parts that make an agent *safe to leave running*: stopping, budgets, ground truth, and transparency.

## The skeleton

```python
@dataclass
class Budget:
    max_iterations: int = 15
    max_cost_usd: float = 2.00
    max_wall_clock_s: float = 300.0

@dataclass
class RunState:
    iterations: int = 0
    cost_usd: float = 0.0
    started: float = field(default_factory=time.monotonic)
    call_signatures: Counter = field(default_factory=Counter)
    transcript: list = field(default_factory=list)

    def elapsed(self) -> float:
        return time.monotonic() - self.started


def run(goal: str, tools, registry, budget=Budget()) -> Outcome:
    state = RunState()
    messages = [{"role": "user", "content": goal}]

    while True:
        stop = check_budget(state, budget)
        if stop:
            return Outcome(status=stop, state=state, result=None)

        response = call_model(messages, tools)
        state.iterations += 1
        state.cost_usd += price(response.usage)
        messages.append(response.message)

        if not response.message.tool_calls:
            return Outcome(status="done", state=state,
                           result=response.message.content)

        for tc in response.message.tool_calls:
            messages.append(run_tool(tc, registry, state))
```

Everything below is a refinement of `check_budget` and `run_tool`.

## Stopping conditions

An iteration cap alone is the minimum and is not enough. Four conditions:

```python
def check_budget(state: RunState, b: Budget) -> str | None:
    if state.iterations >= b.max_iterations:
        return "max_iterations"
    if state.cost_usd >= b.max_cost_usd:
        return "budget_exceeded"
    if state.elapsed() >= b.max_wall_clock_s:
        return "timeout"
    if max(state.call_signatures.values(), default=0) >= 3:
        return "stuck"
    return None
```

**Cost, not iterations, is what hurts.** One call carrying 80K tokens of accumulated context costs more than six small ones. Check cost after each response *and* before the next request — a cap tested only at the top of the loop lets a single expensive iteration blow past it.

**"Stuck" is the most common real failure.** The model calls the same tool with the same arguments, gets the same result, and does it again. Getting stuck is a normal failure mode, not an exotic one.

Before killing a stuck run, try to unstick it in-band — it works often enough to be worth the two lines:

```python
sig = (tc.function.name, tc.function.arguments)
state.call_signatures[sig] += 1
if state.call_signatures[sig] == 2:
    return tool_message(tc, {
        "error": "You already called this tool with these exact arguments and "
                 "got this same result. Try different arguments, use a different "
                 "tool, or answer with what you have."
    })
```

**Hitting a cap is a return value, not an exception.** The caller decides whether a partial run is useful; raising discards the transcript, the token count, and the tool history — the three things you need to understand what happened.

## Budget caps

Workflows get cost control for free from their structure: you can count the calls by reading the code. Agents cannot, so the cap has to be explicit.

```python
def price(usage) -> float:
    return (usage.prompt_tokens / 1e6) * PRICE_IN + \
           (usage.completion_tokens / 1e6) * PRICE_OUT
```

Three things to get right:

- **Include cached-read tokens at their own rate** if your provider prices them separately. Ignoring them overstates cost on cache-heavy runs and hides the savings.
- **Include reasoning tokens.** They bill and they do not appear in the answer. A "cheaper" reasoning model can cost more per task than a pricier non-reasoning one.
- **Count subagent spend against the parent's budget** if the agent can delegate. See `subagents-and-multi-agent`.

For a ceiling the model itself can pace against, Anthropic's task budgets (`output_config.task_budget`, minimum 20,000 tokens) inject a countdown the model sees during generation, so it winds down gracefully rather than being cut off mid-action. That is different from `max_tokens`, which is an enforced per-response ceiling the model knows nothing about. Use both: the task budget for graceful pacing, your own cap as the hard stop.

## Ground truth in the loop

The condition that makes agents work at all: **the environment tells the truth**. Tests pass or fail, a compiler errors, an API returns a real status.

Audit your tool list for this directly. For each tool, ask: does its result reflect the world, or does it reflect the model's own assertion?

```text
run_tests()        → real signal. exit code, failing test names.
read_file()        → real signal. the bytes are the bytes.
search_docs()      → weak signal. relevance is a judgment, and a bad result
                     looks the same as no result.
summarize_state()  → no signal. the model grading its own work.
```

If most steps are in the third category, errors compound with nothing to correct them, and you have an expensive random walk. Erroneous tool calls that go unresolved within a few turns tend to stay unresolved, and accumulated errors degrade reasoning for the rest of the run.

The fix is usually a tool, not a prompt: add the verification step as something the agent can *call* and whose result it must read.

## Transparent planning

An agent whose reasoning you cannot inspect is one you cannot debug or trust. Make the plan an artifact, not an internal state.

```python
{
    "name": "record_plan",
    "description": "State your plan before acting. Call again if the plan changes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "steps": {"type": "array", "items": {"type": "string"}},
            "success_criteria": {"type": "string"},
        },
        "required": ["steps", "success_criteria"],
        "additionalProperties": False,
    },
}
```

A plan expressed as a tool call lands in the transcript, is visible to a human watching, and — critically — makes *deviation from the plan* visible, which is the thing you actually want to see. A plan the model holds internally and abandons silently is worse than no plan.

## What to log

You will debug this from the transcript, so store it as data rather than as a printed string:

```python
{
    "run_id": ..., "goal": ..., "status": "max_iterations",
    "iterations": 15, "cost_usd": 1.84, "elapsed_s": 212,
    "tool_calls": [{"i": 1, "name": "search_logs", "args": {...},
                    "ok": True, "result_tokens": 812}, ...],
    "plan_revisions": 3,
    "transcript": [...],
}
```

`result_tokens` per call is the one people leave out and then want. It tells you which tool is eating the context budget, which is nearly always the first thing to fix. See `tool-design`.

## Human oversight

Guardrails for anything irreversible, in increasing order of strength:

1. **Sandbox first.** Run against a copy — a scratch branch, a staging database, a dry-run flag on every write tool.
2. **Confirmation on destructive tools.** The tool returns "pending approval" and the loop pauses. This is a tool-level decision, not a prompt-level one; a prompt saying "ask before deleting" is not a control.
3. **Structural removal.** The safest version of a dangerous tool is its absence. If the task does not need `delete_records`, do not define it.
4. **Review before effect.** The agent produces a diff, a draft, a proposed change; a human applies it.

Prompt instructions are not guardrails. They are requests, and an agent under pressure to complete a task will occasionally decline them.

## Before you ship it

- [ ] Iteration, cost, and wall-clock caps, all three, all tested by forcing them
- [ ] Repeated-call detection with an in-band nudge before the kill
- [ ] At least one tool per step that returns a real environment signal
- [ ] Plan recorded in the transcript as an artifact
- [ ] Every irreversible action sandboxed, gated, or absent
- [ ] Structured run logs with per-call token counts
- [ ] An eval suite that measures task completion, not just "it ran" (`evals-before-shipping`)
- [ ] A measured comparison against the workflow you would otherwise have written

The last one is the honest test. If the agent does not beat the workflow on your eval set, you have bought latency, cost, and failure modes for nothing — collapse it into the workflow you now know you needed.
