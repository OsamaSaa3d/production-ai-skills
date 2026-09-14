# Orchestrator-Workers Inside One Agent

The pattern for when subtasks are **dependent** — or when they are independent but you want the coordination logic in your code rather than in a model's judgment.

This is the destination for most proposals that arrive labeled "multi-agent." It keeps one control flow, gets parallelism and context isolation where they help, and has no inter-agent negotiation to go wrong.

## Where it sits

| | Orchestrator-workers | Subagents | Separate agents |
|---|---|---|---|
| Control flow | Your code | The model decides when to delegate | Each agent's own |
| Subtasks decided by | A model, at runtime | The model, ad hoc | Each agent |
| Dependencies between subtasks | **Fine** | Awkward | Bad |
| Context isolation | Per worker call | Per subagent | Per agent |
| Debuggability | High — it's a function | Medium | Low |

The distinguishing property against plain parallelization: **the subtasks are determined at runtime rather than predefined.** Topologically it is the same graph; here the model decides the shape of it.

## The structure

```python
class Subtask(BaseModel):
    id: str
    objective: str
    depends_on: list[str] = Field(default_factory=list,
        description="ids of subtasks whose output this one needs")

class Plan(BaseModel):
    subtasks: list[Subtask] = Field(description="At most 6. Order does not matter; "
                                                "express ordering through depends_on.")

async def orchestrate(goal: str) -> str:
    plan = call(SYSTEM_PLANNER, goal, schema=Plan)
    results: dict[str, str] = {}

    for layer in topological_layers(plan.subtasks[:MAX_WORKERS]):
        outputs = await asyncio.gather(*[
            run_worker(task, upstream={d: results[d] for d in task.depends_on})
            for task in layer
        ], return_exceptions=True)

        for task, out in zip(layer, outputs):
            results[task.id] = (out if not isinstance(out, Exception)
                                else f"FAILED: {out}")

    return call(SYSTEM_SYNTHESIZER, goal=goal, results=results)
```

`depends_on` plus topological layering is what makes this handle dependent subtasks at all. Independent subtasks land in one layer and run concurrently; dependent ones serialize, with upstream output passed in explicitly. Multi-agent has no equivalent — separate agents would have to negotiate that ordering between themselves, which is exactly where it falls apart.

## Passing upstream results

A worker only sees what you hand it. Be explicit about *which* upstream output it needs, not all of them:

```python
async def run_worker(task: Subtask, upstream: dict[str, str]) -> str:
    context = "\n\n".join(f"### Output of {k}\n{v}" for k, v in upstream.items())
    return await acall(SYSTEM_WORKER, f"""{task.objective}

{"Upstream findings you must build on:" if context else ""}
{context}

Return at most 300 words. State explicitly anything you could not determine.""")
```

Passing *all* prior results to every worker is the mistake that turns this pattern back into one giant context. Pass only the declared dependencies — that is what the field is for, and it is why you asked the planner to declare them.

## Where the caps go

```python
MAX_WORKERS = 6          # applied by slicing the plan, not by asking nicely
MAX_LAYERS  = 3          # depth of the dependency graph
MAX_RETRIES = 1          # per worker
```

**Slice the plan in code.** `plan.subtasks[:MAX_WORKERS]` is doing real work — a planner asked for "at most 6" will occasionally return eleven. Instructions are not limits.

**Cap the depth.** A dependency chain six deep is six sequential model calls, each carrying the last one's output. That is a latency and cost profile nobody estimated.

**`return_exceptions=True`.** One failed worker should degrade the result, not kill the run. But then you must handle it: a `FAILED:` marker in `results` that the synthesizer is told to surface, not silently drop. An empty findings set synthesizing into a confident answer is the worst outcome available.

## Evaluate the plan as its own step

The orchestrator's decomposition is a model output like any other, and it fails in ways the final answer hides — a confident synthesis of the wrong research looks exactly like a good answer.

```python
def test_plan_quality():
    plan = call(SYSTEM_PLANNER, "Why did checkout conversion drop 12% in September?",
                schema=Plan)
    ids = {s.id for s in plan.subtasks}
    assert 2 <= len(plan.subtasks) <= 6
    assert all(set(s.depends_on) <= ids for s in plan.subtasks)   # no dangling refs
    assert not has_cycle(plan.subtasks)
    assert covers(plan, ["traffic mix", "funnel step timings", "deploys in range"])
```

The structural assertions are free and catch real bugs — dangling dependency ids and cycles both happen. `covers` is the expensive one; write it against a handful of goals where you know the right decomposition. `evals-before-shipping` has `PlanQualityMetric` and `PlanAdherenceMetric` for the model-judged version.

## Synthesis

The step most likely to quietly lose information. Two rules:

**Carry uncertainty through.** Require workers to report what they could not determine, and require the synthesizer to include it. Workers reporting uncertainty and a synthesizer flattening it into confident prose is the characteristic failure of this pattern.

```python
SYSTEM_SYNTHESIZER = """Combine the worker findings into one answer.

Rules:
- Every claim must trace to a specific worker's finding.
- Include a "Gaps" section naming anything the workers could not determine
  and anything marked FAILED.
- Do not add analysis the workers did not support.
- If findings conflict, say so and present both."""
```

**Keep the raw findings.** Log them alongside the synthesis. When the answer is wrong you need to know whether a worker got it wrong or the synthesizer dropped it, and that is not recoverable from the final text.

## When to move up or down

**Down to a plain workflow** when you notice the planner producing the same decomposition every time. That is a fixed pipeline with extra steps and a planning call you are paying for. Hard-code it.

**Up to separate agents** only when workers genuinely need to negotiate — to exchange partial findings, challenge each other, and converge. That is rare, it is roughly 15x the tokens of a chat interaction, and the independence test in `agent-vs-workflow-decision`'s `references/multi-agent.md` is the gate.

**Sideways to subagents** when you want the model to decide *whether* to delegate at all, rather than always decomposing. The orchestrator-workers shape always plans; subagent delegation is discretionary. If most tasks don't need decomposition, the always-plan cost is waste.
