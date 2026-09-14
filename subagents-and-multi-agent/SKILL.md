---
name: subagents-and-multi-agent
description: Use this skill when someone proposes splitting an LLM system into multiple agents — a "multi-agent system," a "crew," a supervisor plus workers, a planner and an executor, or specialist agents per domain. Use it when an agent is running out of context, when tool results or file reads are flooding the transcript, when independent subtasks could run in parallel, or when different parts of a task need different tool permissions. Use it to decide between one agent, one agent with subagents, and genuinely separate coordinating agents. Read agent-vs-workflow-decision first if it is not yet settled that an agent is warranted at all.
---

# Subagents and Multi-Agent Systems

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

Most systems described as "multi-agent" should be **one agent that spawns subagents**. Genuinely independent coordinating agents are a narrow case with a high cost.

A subagent is a fresh agent instance spawned by a parent within the same session. It gets its own context window, its own system prompt, its own tool subset, and optionally its own model. It does a bounded task and returns **only its final message** to the parent. Intermediate tool calls, file reads, and reasoning stay inside it.

That last property is the whole point. Subagents are primarily a **context isolation** mechanism, not an intelligence mechanism. You are not making the system smarter by adding agents; you are keeping the parent's transcript clean.

## What changed: two classic reasons no longer apply

Before reaching for multiple agents, check whether your reason has been absorbed by single-agent features.

| Classic reason to split | Current status |
|---|---|
| Too many tools for one agent | **Largely solved.** `defer_loading` + tool search: definitions drop from ~72K to ~500 tokens upfront, and MCP-eval accuracy rose 49%→74% (Opus 4) and 79.5%→88.1% (Opus 4.5). See `tool-design`. |
| Tool results flooding context | **Largely solved.** Programmatic tool calling keeps intermediate results in a sandbox; ~37% token reduction on complex research tasks. See `tool-design`. |
| Exploration and reasoning flooding context | **Still a real reason.** A subagent that reads thirty files returns a summary, not thirty files. |
| Independent subtasks could run in parallel | **Still a real reason.** N subtasks finish in the time of the slowest, not the sum. |
| Different tool permissions per task | **Still a real reason.** A reviewer subagent with `["Read", "Grep", "Glob"]` structurally cannot write. |
| Specialized domain instructions | **Usually a skill, not an agent.** Only becomes a subagent if it also needs isolation or restriction. |

If your reason is in the top two rows, fix the single agent first. Adding agents to solve a tool-count problem that `defer_loading` already solves buys you coordination failure modes for nothing.

## Subagents: the common case

The examples below use the Claude Agent SDK because it makes the four decisions explicit — name, tool subset, model, return shape. **Nothing in this skill depends on that SDK.** A subagent is a second call to any provider with its own system prompt, its own tool list, and a prompt string from the parent; the sections after this one are about what to put in those, which is portable. Where a concrete option name appears (`AgentDefinition`, `allowed_tools`, `CLAUDE_CODE_*`), read it as "your harness's equivalent."

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition

async for message in query(
    prompt="Review the authentication module for security issues",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],   # Agent tool enables delegation
        agents={
            "code-reviewer": AgentDefinition(
                # description is how the parent decides to invoke it — write it like a tool description
                description="Expert code review specialist. Use for quality, security, and maintainability reviews.",
                prompt="""You are a code review specialist.

When reviewing code:
- Identify security vulnerabilities
- Check for performance issues
- Verify adherence to coding standards

Return a concise findings list. Do not modify files.""",
                tools=["Read", "Grep", "Glob"],   # structurally read-only
                model="sonnet",                    # cheaper model for bounded work
            ),
            "test-runner": AgentDefinition(
                description="Runs and analyzes test suites. Use for test execution and coverage analysis.",
                prompt="You are a test execution specialist. Run tests and report failures with suggested fixes.",
                tools=["Bash", "Read", "Grep"],
            ),
        },
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

Subagents can also be defined as markdown files in `.claude/agents/`, with YAML frontmatter and the body as the system prompt. Programmatic definitions take precedence over filesystem ones with the same name.

The four benefits, in the order they usually matter:

1. **Context isolation** — intermediate work stays inside; only the final message returns.
2. **Parallelization** — independent subagents run concurrently.
3. **Specialized instructions** — domain knowledge that would be noise in the parent's prompt.
4. **Tool restrictions** — a tool omitted from `tools` is not in the subagent's session at all. No permission prompt, no error; it simply cannot happen.

## Know exactly what crosses the boundary

This is where subagent designs fail. A non-fork subagent's context starts **fresh**, and the only thing passed from parent to subagent is the Agent tool's prompt string.

| Subagent receives | Subagent does not receive |
|---|---|
| Its own system prompt + the Agent tool's prompt | The parent's conversation history or tool results |
| Project `CLAUDE.md` | Preloaded skill content, unless listed in `skills` |
| Tool definitions (inherited, or the subset in `tools`) | The parent's system prompt |

**Practical consequence: put every file path, error message, ID, and decision the subagent needs directly in the delegation prompt.** A subagent asked to "fix the bug we discussed" knows nothing about any discussion.

Going the other way, the parent receives the subagent's final message as the Agent tool result — but may summarize it rather than passing it through. If you need verbatim output, say so in the parent's prompt.

Note also that final messages are scanned for instruction-shaped patterns before the parent reads them (control-tag imitation, turn markers like a leading `Human:`). The scan neutralizes formatting rather than removing text, but it means a subagent's output is not a trusted channel into the parent.

## Design subagent tasks to be small and closed

The context savings come from the ratio of work done to summary returned. A subagent that reads 30 files and returns 3 paragraphs is a large win. A subagent that reads one file and returns its contents is pure overhead — you paid for an extra agent instance to move data.

Good subagent tasks are:

- **Bounded** — a clear finish line the subagent can recognize.
- **High compression** — much input, little output. Search, audit, explore, triage, verify.
- **Self-contained** — needs no parent history beyond what fits in the delegation prompt.
- **Independent** — if two subagents need to negotiate, they should be one subagent.

```
Good:  "Search the codebase for every call site of `legacy_auth()`. Return a list of
        file:line locations with a one-line description of each usage context."

Good:  "Run the full test suite. Return only the failing tests, their assertion
        messages, and the most likely cause of each."

Bad:   "Help with the refactor."            (unbounded, no finish line)
Bad:   "Read config.py and tell me what's in it."   (no compression — just read it)
Bad:   "Coordinate with the test-runner agent to decide the approach."  (needs negotiation)
```

Use a cheaper model for bounded work. Subagents inherit the parent's model by default, so a triage subagent left on the default model costs the same per token as the orchestrator.

## Cap depth, concurrency, and spend

Claude decides on its own when to spawn subagents and how many. Subagents can spawn subagents. One prompt can become a tree.

```python
async for message in query(
    prompt="Audit every service in this repo for unhandled promise rejections",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob", "Agent"],
        env={
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",   # subagents can't spawn their own
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "5",
        },
        max_budget_usd=5.0,
    ),
):
    if isinstance(message, ResultMessage):
        print(f"{message.subtype}: ${message.total_cost_usd}")
```

The three caps below are the Claude Agent SDK's; every harness that spawns subagents needs the same three, whatever it calls them. If yours has no budget cap, you own that one — track spend in the loop and stop.

| Limit | Default | Behavior at the limit |
|---|---|---|
| `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` | 3 layers | Bottom-layer subagent does the work itself instead of delegating |
| `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` | 20 | Returns `Concurrent subagent limit reached` until the count drops |
| `max_budget_usd` / `maxBudgetUsd` | none | Refuses new subagents, stops background ones, ends with `error_max_budget_usd` |

**Set all three before running anything unattended.** Subagent requests count toward `total_cost_usd`, so the budget cap is the only hard stop.

Note the SDKs differ on `env`: TypeScript *replaces* the subprocess environment (spread `process.env` to keep `PATH`), Python *merges* into it.

More capable models delegate more readily, so these limits matter more as you move up the model tier, not less.

## Subagent, skill, or separate agent?

Three mechanisms, commonly confused:

- **Skill** — reusable instructions that load into the *main* conversation context. Use when you want the parent itself to behave differently. No isolation, no extra instance, cheapest.
- **Subagent** — isolated instance within one session. Use when work needs its own context window, restricted tools, or parallel execution.
- **Separate coordinating agents** — independent instances across sessions, each with its own context, able to message each other. Use only when one specialist is genuinely not enough *and* they need to talk through a plan.

The default order: **reach for a skill when you want the instructions inline, a subagent when you want the work isolated, and separate agents only when peers must negotiate.**

For orchestrating dozens to hundreds of agents, turn-by-turn delegation stops being the right shape — that work belongs in a script or workflow that runs orchestration outside the conversation context entirely.

## Full multi-agent: the narrow case

Independent coordinating agents earn their cost on **breadth-first problems that decompose into genuinely independent directions**, where total information exceeds one context window.

Anthropic's research system — an orchestrator with parallel subagents — reported roughly 90% improvement over a single agent on their internal research eval, at roughly **15x the tokens of a chat interaction**, with token usage explaining most of the performance variance.

The documented limit: domains requiring all agents to share the same context, or involving many dependencies between agents, are not a good fit. Coding is the canonical bad fit — subtasks are tightly interdependent.

**The test: if the subtasks are not independent, you want orchestrator-workers inside one agent, not separate agents.**

Costs compound badly. A subagent that recursively spawns more subagents, or a tool returning oversized results, can multiply a run by another order of magnitude. Context gets re-passed and re-billed at every handoff. Per-agent cost estimates routinely undershoot.

## Pitfalls

**Role-play multi-agent.** A "researcher," a "writer," and a "critic" sharing one context is one model talking to itself at several times the cost. If they share context and depend on each other, collapse them.

**Splitting to solve a tool-count problem.** Try `defer_loading` and tool search first. Splitting agents to reduce tool count adds coordination failures to solve something a flag fixes.

**Assuming the subagent knows anything.** It does not have the parent's history. Everything needed goes in the delegation prompt.

**Subagents that don't compress.** If the summary is nearly as long as the input, you added an agent instance for nothing.

**No caps on an unattended run.** Depth, concurrency, and budget. All three.

**Leaving subagents on the parent's model.** Bounded triage work does not need the orchestrator's model tier.

**Vague `description` fields.** The parent decides delegation from the description, exactly as it decides tool calls from tool descriptions. Same rules apply — see `tool-design`. If the parent isn't delegating, the description is usually why; naming the subagent explicitly in the prompt bypasses matching and confirms the diagnosis.

**No evals on the delegation decision.** Whether the parent delegates to the right subagent is a tool-selection problem and is measurable the same way. See `evals-before-shipping`.

## References

- `references/subagent-patterns.md` — starter roster: explore, triage, verify, audit, with prompts and tool sets
- `references/delegation-prompts.md` — writing the Agent-tool prompt so the subagent has what it needs
- `references/orchestrator-workers.md` — the single-agent orchestration pattern, for when subtasks are dependent
- `references/cost-control.md` — caps, model tiering, measuring compression ratio per subagent
- `references/multi-agent.md` — genuinely separate agents: independence test, handoffs, coordination failures