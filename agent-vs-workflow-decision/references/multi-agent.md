# Multi-Agent: Structure, Test, and Cost Controls

Multi-agent is not "an agent, but better." It is a specific architecture for a specific shape of problem, and it is the most expensive rung on the ladder. This file is the decision, the structure, and the controls — for the subagent mechanics themselves, see `subagents-and-multi-agent`.

## The independence test

Run it before anything else. Everything downstream depends on the answer.

> **Can each subtask be completed without knowing what the others found?**

Independent — decompose:

```text
"Research the competitive landscape for X"
  → pricing across five competitors
  → public funding history
  → published customer counts
Each direction is answerable alone. Findings combine at the end.
```

Dependent — do not decompose:

```text
"Refactor the auth module and update its callers"
  → rename the function        ← callers depend on the new name
  → update call sites          ← depends on the rename being done
  → update the tests           ← depends on both
Every subtask needs the others' output. This is a pipeline.
```

Anthropic states the limit directly: domains requiring all agents to share the same context, or involving many dependencies between agents, are not a good fit for multi-agent systems today. **Coding is the canonical bad fit** — subtasks are tightly interdependent, which is exactly the property that breaks the architecture.

If the subtasks are not independent, you want orchestrator-workers inside one agent. See `workflow-patterns.md`.

## What it buys, and at what price

Anthropic's research system — an orchestrator with parallel subagents — reported roughly a **90% improvement over a single agent** on their internal research eval, at roughly **15x the tokens of a chat interaction**, with token usage explaining most of the performance variance.

Read that last clause carefully. If token spend is the dominant variable, then the architecture is a way of *buying* performance with tokens, not a cleverness that makes tokens go further. The question becomes economic: is a 90% lift on this task worth 15x on this budget? For research, where the output is valuable and the alternative is hours of human work, frequently yes. For a support reply, no.

Rough comparison, same task shape:

| Architecture | Relative tokens |
|---|---|
| Single call | 1x |
| Chat interaction | ~4x |
| Agent | ~15x of a single call (~4x a chat interaction) |
| Multi-agent | ~15x a chat interaction |

Estimate before you build. See `cost-modeling.md`.

## The structure

Orchestrator, parallel workers, synthesis. Workers do not talk to each other — if they need to, they are not independent and you are back at the test.

```python
class Plan(BaseModel):
    subtasks: list[Subtask] = Field(description="Independent directions, at most 5.")

class Subtask(BaseModel):
    objective: str = Field(description="What this worker must determine.")
    context: str = Field(description="Every fact the worker needs. It sees nothing else.")
    done_when: str = Field(description="How the worker knows it has finished.")

async def orchestrate(goal: str, budget: RunBudget) -> str:
    plan = call(SYSTEM_ORCHESTRATOR, goal, schema=Plan)
    subtasks = plan.subtasks[:MAX_WORKERS]                    # hard cap, always

    results = await asyncio.gather(*[
        run_worker(s, budget.per_worker) for s in subtasks
    ], return_exceptions=True)

    findings = [r for r in results if not isinstance(r, Exception)]
    if not findings:
        raise NoUsableFindings(goal)
    return call(SYSTEM_SYNTHESIZER, goal=goal, findings=findings)
```

Three details doing real work:

**`context` as a required field.** A worker starts fresh. It does not have the orchestrator's conversation, its tool results, or its reasoning. The single most common multi-agent bug is a delegation prompt that assumes shared knowledge — "fix the bug we discussed" delegated to something that has never heard of any discussion.

**`done_when` as a required field.** Workers without a finish line burn their whole budget. Making the orchestrator state the criterion forces it to think about scope at planning time.

**`return_exceptions=True`.** One worker failing should degrade the result, not kill the run. Synthesize from what came back and say what is missing.

## Cost controls

Costs compound badly and in ways per-agent estimates miss. A subagent that recursively spawns more subagents, or a tool returning oversized results, can multiply a run by another order of magnitude.

```python
@dataclass
class RunBudget:
    total_usd: float = 10.0
    per_worker_usd: float = 1.50
    max_workers: int = 5
    max_depth: int = 1          # workers cannot spawn their own workers
```

Four controls, all of which are load-bearing:

1. **A hard worker cap, applied by slicing the plan.** Not a prompt instruction. An unbounded planner will occasionally return forty subtasks.
2. **A depth cap.** Workers spawning workers turns one prompt into a tree with no ceiling. Depth 1 unless you have a specific reason.
3. **A per-worker budget** enforced inside each worker's own loop, plus a total checked as results come back.
4. **A circuit breaker on the total**, killing in-flight workers when the run budget is exhausted. Without this, the caps above are advisory — you discover the overrun after paying for it.

On the Claude Agent SDK these map to `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, and `max_budget_usd`. Set all three before running anything unattended; the budget cap is the only hard stop.

## Where the tokens actually go

Worth knowing, because the intuitive model is wrong:

- **Re-passed context.** Every handoff re-bills the context it carries. An orchestrator that passes a growing brief to each of five workers pays for it five times.
- **Coordination overhead.** Planning and synthesis are model calls with no task output. On short tasks this is most of the bill.
- **Retries.** A failed worker redoes its whole context, not just the failed step.
- **Oversized tool results.** A worker whose search tool returns 200 rows pays for 200 rows on every subsequent turn of that worker's loop. This is usually the single largest line item, and it is a tool-design bug rather than an architecture one. See `tool-design`.

The fourth is the one to check first when a run costs three times your estimate.

## The role-play anti-pattern

Spawning a "researcher," a "writer," and a "critic" with different personas **in one shared context** is not multi-agent architecture. It is one model talking to itself with a costume change between turns, at several times the token cost, with no isolation and no parallelism.

The diagnostic is mechanical: **do the personas have separate context windows?** If they are turns in one conversation, collapse them. What you wanted was either an evaluator-optimizer workflow (if the critique loop is the point) or a better system prompt.

## Failure modes specific to this architecture

**The orchestrator hallucinates the decomposition.** It produces five plausible subtasks that do not cover the question. You get a confident synthesis of the wrong research. Mitigation: evaluate the *plan* as its own step, against known-good decompositions.

**Workers duplicate each other.** Two subtasks phrased differently produce the same searches. Mitigation: state in the orchestrator prompt that subtasks must not overlap, and log the actual tool calls per worker to check.

**Synthesis loses the caveats.** Workers report uncertainty; the synthesizer flattens it into confident prose. Mitigation: require a `confidence` and `gaps` field per worker finding, and require the synthesizer to carry them through.

**A worker fails silently.** With `return_exceptions=True` and no check, an empty finding list synthesizes into a confident answer built on nothing. Mitigation: the `if not findings` guard above, plus naming the failed subtasks in the output.

## The honest comparison

Before shipping, run the same task set through:

1. A single agent with the same tools.
2. Orchestrator-workers inside one agent.
3. The multi-agent version.

Record pass rate, cost per task, and wall-clock. Multi-agent has to beat both alternatives by enough to justify 15x. Frequently option 2 is within a few points at a fraction of the cost — which is the outcome you want to discover before launch, not after the first invoice.
