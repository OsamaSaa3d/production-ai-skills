---
name: agent-vs-workflow-decision
description: >-
  Use before writing code when the user asks for an "agent," "AI assistant," "copilot," "autonomous
  system," "multi-agent system," or any multi-step LLM system. Use it when a process should be automated
  with an LLM, when extending existing agent-loop code, or when someone proposes a second agent, a
  supervisor, or a "crew." Decides the architecture — single call, workflow, or agent — before
  implementation. Apply it even when the user already said "agent" — the request usually describes a
  workflow.
metadata:
  version: 1.0
---

# Choosing Between a Single Call, a Workflow, and an Agent

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

Find the simplest architecture that solves the problem, and add complexity only when it demonstrably improves outcomes. Most systems people describe as agents are workflows. Many workflows are a single well-constructed LLM call with retrieval and good examples.

The architectural distinction that matters:

- **Workflow** — LLMs and tools orchestrated through predefined code paths. *You* own the control flow. The steps are in your code.
- **Agent** — the LLM dynamically directs its own process and tool usage, deciding what to do next from environment feedback. *You* own the goal, the tools, and the guardrails; the model owns the path.

Agentic systems trade latency and cost for task performance. That trade is worth making sometimes. It is not worth making by default, and "the user said the word agent" is not evidence that it is.

## Avoid / Prefer

| Avoid | Prefer |
|---|---|
| An agent over a fixed procedure | A workflow with the steps in your code |
| Multi-agent for interdependent subtasks | An orchestrator-workers workflow |
| Role-play personas sharing one context | One call with a better prompt |
| A framework as the starting point | Direct API calls |
| An agent as a fix for a wrong answer | Better prompt, retrieval, examples |
| An autonomy loop for a knowledge gap | A skill, loaded context, or tools |
| An unbounded loop | Iteration and per-run budget ceilings |

These are defaults, not laws; the rest of this file explains what each rung costs and when the more complex side is the right call.

## Minimal pattern

```text
Can you write the steps down?
    |
    v
Yes -- write them down: that is a workflow, in your code
    |
    v
No -- does the environment give ground truth at each step?
    |
    v
Yes -- an agent, with stopping conditions and a budget cap
    |
    v
Are the subtasks independent and larger than one context window?
    |
    v
Only then multi-agent, and only once evals beat the workflow
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## The escalation ladder

Start at the top. Move down only when the current rung provably fails on your evals.

1. **Single LLM call.** A good prompt, retrieval, in-context examples. For a large share of applications this is sufficient and nothing further is warranted.
2. **Augmented single call.** One call with tools, retrieval, and memory available — the model can search, call a function, and decide what to keep, but there is no loop.
3. **Workflow.** Multiple calls through code paths you wrote. Predictable, traceable, cheap to debug. Five patterns cover nearly everything; see below.
4. **Agent.** A loop where the model chooses the next action until a stopping condition. Use when you cannot predict the steps.
5. **Multi-agent.** An orchestrator delegating to subagents with separate context windows. A high bar, rarely cleared.

Each rung costs more, fails in more ways, and is harder to debug than the one above it. Skipping rungs is the most common architectural error in LLM applications.

## The decision test

Ask, in order:

**Can you write down the steps?** If yes, write them down — that is a workflow, and your code should contain them. Do not hand a fixed procedure to a model and hope it follows the procedure.

**Is the number of steps predictable?** If the path is known but the count varies within a narrow range, a workflow with a loop still works. If the count genuinely depends on what is discovered mid-task — how many files need changing, how many sources need checking — that is agent territory.

**Do you have ground truth at each step?** Agents work when the environment tells the truth: tests pass or fail, a compiler errors, a tool returns a result. Without a real signal at each step, the agent is guessing in a loop and errors compound silently.

**Do you trust the model's decisions here, and is the environment safe if it is wrong?** Agent autonomy is only appropriate in environments where a wrong decision is recoverable. Sandbox first, extensive testing, guardrails.

**Can you afford it?** Agents run roughly 4x the tokens of a chat interaction; multi-agent systems run roughly 15x. If the value of the output does not clear that multiplier, the architecture is wrong regardless of how well it works.

Four yeses and a budget means an agent. Anything else means a workflow.

## The workflow patterns

Five patterns cover almost every case. Each is a few lines of orchestration code, not a framework.

**Prompt chaining.** Decompose into fixed sequential steps, each call processing the previous output, with programmatic gates between steps to check the process is on track. Use when the task decomposes cleanly into fixed subtasks. Trades latency for accuracy by making each individual call easier.

**Routing.** Classify the input, then dispatch to a specialized downstream prompt, model, or pipeline. Use when there are distinct input categories better handled separately and classification is reliable. Also the right pattern for cost control: route easy inputs to a small fast model and hard ones to a large model.

**Parallelization.** Two variants. *Sectioning* splits a task into independent subtasks run concurrently — one model handles the response while another screens for policy violations, which works better than asking one call to do both. *Voting* runs the same task several times for diverse outputs, then aggregates — useful for review and moderation where you want to tune the false-positive/false-negative balance with a vote threshold.

**Orchestrator-workers.** A central LLM breaks the task into subtasks, delegates them, and synthesizes results. Topologically similar to parallelization, but the subtasks are *determined at runtime* rather than predefined. Use when you cannot know the subtasks in advance.

**Evaluator-optimizer.** One call generates, another critiques, in a loop. Use when you have clear evaluation criteria and iterative refinement measurably helps. Two signs of fit: a human articulating feedback would improve the output, and an LLM can produce that feedback.

Note that orchestrator-workers and evaluator-optimizer already contain model-driven decisions. The line between "complex workflow" and "agent" is a gradient, not a wall. What matters is how much of the control flow lives in your code.

## When an agent is actually right

Agents fit open-ended problems where you cannot predict the number of steps and cannot hardcode a path. The model operates for many turns, and you must have real trust in its decision-making.

The conditions that make agents work, all of which are present in coding and absent in most business processes:

- **Verifiable output.** Tests, compilers, linters — an objective signal that the work is correct.
- **Feedback loops.** The agent can act, observe the real result, and correct.
- **Well-defined problem space.** Structured, with clear boundaries.
- **Meaningful human oversight.** Review before anything irreversible.

Coding agents and customer support are the two domains that consistently clear this bar — support because interactions are conversational but need real actions (pull customer data, issue a refund, update a ticket) and success is measurable as resolution.

If you build one, include stopping conditions. A maximum iteration count is the minimum. Agents without a ceiling burn budget when they get stuck, and getting stuck is a normal failure mode rather than an exotic one.

## Multi-agent: the high bar

Multi-agent is not "an agent, but better." It is a specific architecture for a specific shape of problem, and it is expensive.

**When it earns its cost:** breadth-first problems that decompose into genuinely *independent* directions, where the total information exceeds one context window. Anthropic's research system uses an orchestrator with parallel subagents and reports a ~90% improvement over a single agent on their internal research eval — at roughly 15x the tokens of a chat interaction, with token usage explaining most of the performance variance.

**When it does not:** Anthropic states the limit directly — domains that require all agents to share the same context, or that involve many dependencies between agents, are not a good fit for multi-agent systems today. Coding is the canonical example of a badly-fitting task, because the subtasks are tightly interdependent.

The cost multiplier compounds badly when something misbehaves. A subagent that spawns more subagents, or a tool returning oversized results, can multiply a single run by another order of magnitude. Add per-run budget caps and circuit breakers; do not assume the published architectures have them.

The test: **if the subtasks are not independent, you want an orchestrator-workers workflow, not multi-agent.** Most "multi-agent" proposals are one agent with a role-play prompt layered on, which adds tokens and coordination failure modes while buying nothing.

## Skills, not agents

Before adding an agent, ask whether the problem is actually a *knowledge* gap rather than an *autonomy* gap.

If the model would do the task correctly given the right instructions, conventions, or domain context, the answer is better context — a skill, a loaded procedure document, retrieval over your internal docs — not an autonomous loop. Loading the right instructions on demand is cheaper, more predictable, and easier to version than an agent that has to discover the same information at runtime.

Rough split:

- **Needs a skill:** the task is well-defined but the model lacks your conventions, house style, domain rules, or process knowledge.
- **Needs tools:** the model knows what to do but cannot reach the data or perform the action.
- **Needs a workflow:** the steps are known and there are several of them.
- **Needs an agent:** the steps are genuinely unknowable in advance.

These compose. An agent with well-designed tools and a good skill beats an agent with neither, and often a skill plus tools removes the need for the agent.

## Invest in the agent-computer interface

If you build an agent, the tools are the product. Give tool definitions as much prompt-engineering attention as the system prompt — on the SWE-bench agent, Anthropic reports spending more time optimizing the tools than the overall prompt.

Concretely:

- Write tool descriptions like docstrings for a new engineer: what it does, when to use it, edge cases, input format, clear boundaries from similar tools.
- Choose formats the model writes naturally. Diffs require counting lines before writing; JSON-wrapped code requires escaping. Both invite errors that markdown does not.
- Leave room to think before the model commits to a format it cannot back out of.
- Poka-yoke the arguments — make the mistake impossible rather than documenting it. Absolute filepaths instead of relative ones removed an entire failure class in Anthropic's SWE-bench agent.
- Test with many real inputs and iterate on the tools based on observed mistakes.

## Don't do this

**Building an agent because the user said "agent."** The word describes an aspiration, not an architecture. Find out what the system actually needs to do, then pick the rung.

**Role-play multi-agent.** Spawning a "researcher," a "writer," and a "critic" with different personas in one shared context is not multi-agent architecture — it is one model talking to itself at several times the token cost. If the agents share context and depend on each other, collapse them.

**Agent loops over fixed procedures.** If the steps are known, an agent that rediscovers them every run is a slower, costlier, less reliable version of a for-loop.

**Reaching for a framework first.** Frameworks add abstraction layers that obscure the actual prompts and responses, make debugging harder, and make it tempting to add complexity where a simpler setup would do. Start with the LLM API directly — most of these patterns are a few lines of code. If you do use one, understand what it does underneath; incorrect assumptions about framework internals are a common source of error.

**Adding an agent to fix an accuracy problem.** If a single call gets the wrong answer, an agent usually gets the wrong answer more expensively. Fix the prompt, the retrieval, or the examples first.

## Common pitfalls

**No stopping condition.** Cap iterations. Always.

**No budget ceiling.** Per-run token and cost caps, with a circuit breaker. Workflows get this for free from their structure; agents do not.

**Hidden planning.** Prioritize transparency — show the agent's planning steps explicitly. An agent whose reasoning you cannot inspect is one you cannot debug or trust.

**No ground truth in the loop.** If each step's result is the model's own assertion rather than an environment signal, errors compound with nothing to correct them. Erroneous tool calls that are not resolved within a few turns tend to stay unresolved, and accumulated errors degrade the model's reasoning for the rest of the run.

**Skipping evals.** You cannot tell whether the extra complexity helped without measuring. Add complexity only when it demonstrably improves outcomes — which requires the measurement to exist first.

**Treating cost as a pricing problem.** Multi-step cost is an architecture problem. Context gets re-passed and re-billed at every handoff, retries redo work, and the orchestrator burns tokens just coordinating. Per-agent estimates routinely undershoot the real bill.

## When to break the rules

- **Prototyping to learn the problem shape.** Build the agent, watch what it actually does, then collapse it into the workflow you now know you needed.
- **The task genuinely is open-ended** and you have verifiable output and a safe environment. Then take the cost.
- **A framework is already load-bearing** in the codebase and removing it costs more than keeping it.

## Success criteria

The architecture choice is a hypothesis. These are the numbers that say whether the rung you picked was the right one, measured against the simpler rung you rejected:

- **Task completion rate** on the same golden set, run against both architectures — the trajectory metrics in `evals-before-shipping/references/tracing-setup.md` are the ones that read a whole run rather than a single answer
- **Tokens and dollars per successful task**, retries included, against the 4x and 15x multipliers this file quotes
- **Steps per task and redundant-step count** — an agent rediscovering a fixed procedure shows up here first
- **p50 and p95 latency per task**, since latency is half of what an agent trades away
- **Share of runs hitting the iteration cap or budget ceiling** — a high number means stuck runs are your normal case, not an exotic one
- **Share of steps backed by an environment signal** rather than the model's own assertion

If task completion does not move while cost and latency do, the extra rung did not earn its place — collapse it. Unmeasured architecture is decoration.

## References

- `references/workflow-patterns.md` — implementation sketches for all five patterns, in direct API calls
- `references/agent-loop.md` — a minimal agent loop with stopping conditions, budget caps, and transparent planning
- `references/multi-agent.md` — orchestrator-worker structure, independence test, cost controls
- `references/tool-design.md` — the ACI checklist in full, with before/after examples
- `references/cost-modeling.md` — estimating token cost per architecture before you build it