[init] cwd=C:\tmp\skills-eval\arm-b\t16-r2 model=claude-sonnet-5 mcp=[] plugins=[] skills=['agent-vs-workflow-decision', 'context-and-memory', 'evals-before-shipping', 'llm-tool-calling', 'model-selection', 'rag-pipeline-standard', 'structured-output', 'subagents-and-multi-agent', 'system-prompt-engineering', 'tool-design', 'design', 'design-sync', 'dataviz', 'update-config', 'verify', 'debug', 'code-review', 'simplify', 'batch', 'fewer-permission-prompts', 'doctor', 'loop', 'schedule', 'claude-api', 'run', 'run-skill-generator']
[tool_use] Bash {"command": "cd \"C:\\tmp\\skills-eval\\arm-b\\t16-r2\" && ls -la", "description": "List contents of working directory"}
[tool_result] total 8
drwxr-xr-x 1 Osama 197121 0 Sep 15 19:44 .
drwxr-xr-x 1 Osama 197121 0 Sep 15 19:44 ..
drwxr-xr-x 1 Osama 197121 0 Sep 15 19:44 .claude
[tool_use] Bash {"command": "cd \"C:\\tmp\\skills-eval\\arm-b\\t16-r2\" && find .claude -type f | head -100", "description": "List files inside .claude directory"}
[tool_result] .claude/skills/agent-vs-workflow-decision/references/agent-loop.md
.claude/skills/agent-vs-workflow-decision/references/cost-modeling.md
.claude/skills/agent-vs-workflow-decision/references/multi-agent.md
.claude/skills/agent-vs-workflow-decision/references/tool-design.md
.claude/skills/agent-vs-workflow-decision/references/workflow-patterns.md
.claude/skills/agent-vs-workflow-decision/SKILL.md
.claude/skills/context-and-memory/references/context-management.md
.claude/skills/context-and-memory/references/learned-rules.md
.claude/skills/context-and-memory/references/memory.md
.claude/skills/context-and-memory/SKILL.md
.claude/skills/evals-before-shipping/references/ci-integration.md
.claude/skills/evals-before-shipping/references/custom-metrics.md
.claude/skills/evals-before-shipping/references/rag-suite.md
.claude/skills/evals-before-shipping/references/tool-call-suite.md
.claude/skills/evals-before-shipping/references/tracing-setup.md
.claude/skills/evals-before-shipping/SKILL.md
.claude/skills/llm-tool-calling/references/agent-loop.md
.claude/skills/llm-tool-calling/references/anthropic-format.md
.claude/skills/llm-tool-calling/references/many-tools.md
.claude/skills/llm-tool-calling/references/openai-format.md
.claude/skills/llm-tool-calling/references/raw-http.md
.claude/skills/llm-tool-calling/references/why-not-frameworks.md
.claude/skills/llm-tool-calling/SKILL.md
.claude/skills/model-selection/references/capability-matrix.md
.claude/skills/model-selection/references/cost-modeling.md
.claude/skills/model-selection/references/escalation-ladder.md
.claude/skills/model-selection/references/openrouter-models.md
.claude/skills/model-selection/references/routing.md
.claude/skills/model-selection/SKILL.md
.claude/skills/rag-pipeline-standard/references/agentic-retrieval.md
.claude/skills/rag-pipeline-standard/references/chunking.md
.claude/skills/rag-pipeline-standard/references/contextual-retrieval.md
.claude/skills/rag-pipeline-standard/references/document-level-retrieval.md
.claude/skills/rag-pipeline-standard/references/evaluation.md
.claude/skills/rag-pipeline-standard/references/query-rewriting.md
.claude/skills/rag-pipeline-standard/references/rag-vs-tools.md
.claude/skills/rag-pipeline-standard/references/reranking-cross-encoder.md
.claude/skills/rag-pipeline-standard/references/retrieval-bm25-dense-hybrid.md
.claude/skills/rag-pipeline-standard/references/vector-store-selection.md
.claude/skills/rag-pipeline-standard/references/worked-examples.md
.claude/skills/rag-pipeline-standard/SKILL.md
.claude/skills/structured-output/references/classification-patterns.md
.claude/skills/structured-output/references/extraction-patterns.md
.claude/skills/structured-output/references/failure-handling.md
.claude/skills/structured-output/references/raw-schemas.md
.claude/skills/structured-output/references/vs-tool-calling.md
.claude/skills/structured-output/SKILL.md
.claude/skills/subagents-and-multi-agent/references/cost-control.md
.claude/skills/subagents-and-multi-agent/references/delegation-prompts.md
.claude/skills/subagents-and-multi-agent/references/multi-agent.md
.claude/skills/subagents-and-multi-agent/references/orchestrator-workers.md
.claude/skills/subagents-and-multi-agent/references/subagent-patterns.md
.claude/skills/subagents-and-multi-agent/SKILL.md
.claude/skills/system-prompt-engineering/references/agents-md.md
.claude/skills/system-prompt-engineering/references/altitude-examples.md
.claude/skills/system-prompt-engineering/references/behavior-knobs.md
.claude/skills/system-prompt-engineering/references/caching-and-assembly.md
.claude/skills/system-prompt-engineering/references/eval-and-versioning.md
.claude/skills/system-prompt-engineering/references/metaprompting.md
.claude/skills/system-prompt-engineering/references/prompt-injection.md
.claude/skills/system-prompt-engineering/references/prompt-skeleton.md
.claude/skills/system-prompt-engineering/SKILL.md
.claude/skills/tool-design/references/eval-loop.md
.claude/skills/tool-design/references/input-examples.md
.claude/skills/tool-design/references/naming-experiments.md
.claude/skills/tool-design/references/programmatic-calling.md
.claude/skills/tool-design/references/tool-search.md
.claude/skills/tool-design/SKILL.md
[assistant] This request — build something that takes a failing test and autonomously fixes it — is exactly the kind of "build an agent" task the `agent-vs-workflow-decision` skill governs. Let me consult it before deciding on an architecture.
[tool_use] Skill {"skill": "agent-vs-workflow-decision", "args": "Task: build a tool that takes a failing test in a repo and iterates until it passes (run test, read error, edit code, re-run, repeat until green or give up). Deciding whether this should be a workflow or an agent loop, and how to scope it."}
[tool_result] Launching skill: agent-vs-workflow-decision
[user] Base directory for this skill: C:\tmp\skills-eval\arm-b\t16-r2\.claude\skills\agent-vs-workflow-decision

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

ARGUMENTS: Task: build a tool that takes a failing test in a repo and iterates until it passes (run test, read error, edit code, re-run, repeat until green or give up). Deciding whether this should be a workflow or an agent loop, and how to scope it.
[tool_use] Read {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\.claude\\skills\\agent-vs-workflow-decision\\references\\agent-loop.md"}
[tool_result] 1	# A Minimal Agent Loop You Can Defend
2	
3	> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.
4	
5	You have decided the steps are genuinely unknowable and the environment gives real feedback. This is what the loop needs before it runs unattended.
6	
7	For the tool-calling mechanics — message accumulation, parallel calls, tool errors — see `llm-tool-calling/references/agent-loop.md`. This file covers the parts that make an agent *safe to leave running*: stopping, budgets, ground truth, and transparency.
8	
9	## The skeleton
10	
11	```python
12	@dataclass
13	class Budget:
14	    max_iterations: int = 15
15	    max_cost_usd: float = 2.00
16	    max_wall_clock_s: float = 300.0
17	
18	@dataclass
19	class RunState:
20	    iterations: int = 0
21	    cost_usd: float = 0.0
22	    started: float = field(default_factory=time.monotonic)
23	    call_signatures: Counter = field(default_factory=Counter)
24	    transcript: list = field(default_factory=list)
25	
26	    def elapsed(self) -> float:
27	        return time.monotonic() - self.started
28	
29	
30	def run(goal: str, tools, registry, budget=Budget()) -> Outcome:
31	    state = RunState()
32	    messages = [{"role": "user", "content": goal}]
33	
34	    while True:
35	        stop = check_budget(state, budget)
36	        if stop:
37	            return Outcome(status=stop, state=state, result=None)
38	
39	        response = call_model(messages, tools)
40	        state.iterations += 1
41	        state.cost_usd += price(response.usage)
42	        messages.append(response.message)
43	
44	        if not response.message.tool_calls:
45	            return Outcome(status="done", state=state,
46	                           result=response.message.content)
47	
48	        for tc in response.message.tool_calls:
49	            messages.append(run_tool(tc, registry, state))
50	```
51	
52	Everything below is a refinement of `check_budget` and `run_tool`.
53	
54	## Stopping conditions
55	
56	An iteration cap alone is the minimum and is not enough. Four conditions:
57	
58	```python
59	def check_budget(state: RunState, b: Budget) -> str | None:
60	    if state.iterations >= b.max_iterations:
61	        return "max_iterations"
62	    if state.cost_usd >= b.max_cost_usd:
63	        return "budget_exceeded"
64	    if state.elapsed() >= b.max_wall_clock_s:
65	        return "timeout"
66	    if max(state.call_signatures.values(), default=0) >= 3:
67	        return "stuck"
68	    return None
69	```
70	
71	**Cost, not iterations, is what hurts.** One call carrying 80K tokens of accumulated context costs more than six small ones. Check cost after each response *and* before the next request — a cap tested only at the top of the loop lets a single expensive iteration blow past it.
72	
73	**"Stuck" is the most common real failure.** The model calls the same tool with the same arguments, gets the same result, and does it again. Getting stuck is a normal failure mode, not an exotic one.
74	
75	Before killing a stuck run, try to unstick it in-band — it works often enough to be worth the two lines:
76	
77	```python
78	sig = (tc.function.name, tc.function.arguments)
79	state.call_signatures[sig] += 1
80	if state.call_signatures[sig] == 2:
81	    return tool_message(tc, {
82	        "error": "You already called this tool with these exact arguments and "
83	                 "got this same result. Try different arguments, use a different "
84	                 "tool, or answer with what you have."
85	    })
86	```
87	
88	**Hitting a cap is a return value, not an exception.** The caller decides whether a partial run is useful; raising discards the transcript, the token count, and the tool history — the three things you need to understand what happened.
89	
90	## Budget caps
91	
92	Workflows get cost control for free from their structure: you can count the calls by reading the code. Agents cannot, so the cap has to be explicit.
93	
94	```python
95	def price(usage) -> float:
96	    return (usage.prompt_tokens / 1e6) * PRICE_IN + \
97	           (usage.completion_tokens / 1e6) * PRICE_OUT
98	```
99	
100	Three things to get right:
101	
102	- **Include cached-read tokens at their own rate** if your provider prices them separately. Ignoring them overstates cost on cache-heavy runs and hides the savings.
103	- **Include reasoning tokens.** They bill and they do not appear in the answer. A "cheaper" reasoning model can cost more per task than a pricier non-reasoning one.
104	- **Count subagent spend against the parent's budget** if the agent can delegate. See `subagents-and-multi-agent`.
105	
106	For a ceiling the model itself can pace against, Anthropic's task budgets (`output_config.task_budget`, minimum 20,000 tokens) inject a countdown the model sees during generation, so it winds down gracefully rather than being cut off mid-action. That is different from `max_tokens`, which is an enforced per-response ceiling the model knows nothing about. Use both: the task budget for graceful pacing, your own cap as the hard stop.
107	
108	## Ground truth in the loop
109	
110	The condition that makes agents work at all: **the environment tells the truth**. Tests pass or fail, a compiler errors, an API returns a real status.
111	
112	Audit your tool list for this directly. For each tool, ask: does its result reflect the world, or does it reflect the model's own assertion?
113	
114	```text
115	run_tests()        → real signal. exit code, failing test names.
116	read_file()        → real signal. the bytes are the bytes.
117	search_docs()      → weak signal. relevance is a judgment, and a bad result
118	                     looks the same as no result.
119	summarize_state()  → no signal. the model grading its own work.
120	```
121	
122	If most steps are in the third category, errors compound with nothing to correct them, and you have an expensive random walk. Erroneous tool calls that go unresolved within a few turns tend to stay unresolved, and accumulated errors degrade reasoning for the rest of the run.
123	
124	The fix is usually a tool, not a prompt: add the verification step as something the agent can *call* and whose result it must read.
125	
126	## Transparent planning
127	
128	An agent whose reasoning you cannot inspect is one you cannot debug or trust. Make the plan an artifact, not an internal state.
129	
130	```python
131	{
132	    "name": "record_plan",
133	    "description": "State your plan before acting. Call again if the plan changes.",
134	    "input_schema": {
135	        "type": "object",
136	        "properties": {
137	            "steps": {"type": "array", "items": {"type": "string"}},
138	            "success_criteria": {"type": "string"},
139	        },
140	        "required": ["steps", "success_criteria"],
141	        "additionalProperties": False,
142	    },
143	}
144	```
145	
146	A plan expressed as a tool call lands in the transcript, is visible to a human watching, and — critically — makes *deviation from the plan* visible, which is the thing you actually want to see. A plan the model holds internally and abandons silently is worse than no plan.
147	
148	## What to log
149	
150	You will debug this from the transcript, so store it as data rather than as a printed string:
151	
152	```python
153	{
154	    "run_id": ..., "goal": ..., "status": "max_iterations",
155	    "iterations": 15, "cost_usd": 1.84, "elapsed_s": 212,
156	    "tool_calls": [{"i": 1, "name": "search_logs", "args": {...},
157	                    "ok": True, "result_tokens": 812}, ...],
158	    "plan_revisions": 3,
159	    "transcript": [...],
160	}
161	```
162	
163	`result_tokens` per call is the one people leave out and then want. It tells you which tool is eating the context budget, which is nearly always the first thing to fix. See `tool-design`.
164	
165	## Human oversight
166	
167	Guardrails for anything irreversible, in increasing order of strength:
168	
169	1. **Sandbox first.** Run against a copy — a scratch branch, a staging database, a dry-run flag on every write tool.
170	2. **Confirmation on destructive tools.** The tool returns "pending approval" and the loop pauses. This is a tool-level decision, not a prompt-level one; a prompt saying "ask before deleting" is not a control.
171	3. **Structural removal.** The safest version of a dangerous tool is its absence. If the task does not need `delete_records`, do not define it.
172	4. **Review before effect.** The agent produces a diff, a draft, a proposed change; a human applies it.
173	
174	Prompt instructions are not guardrails. They are requests, and an agent under pressure to complete a task will occasionally decline them.
175	
176	## Before you ship it
177	
178	- [ ] Iteration, cost, and wall-clock caps, all three, all tested by forcing them
179	- [ ] Repeated-call detection with an in-band nudge before the kill
180	- [ ] At least one tool per step that returns a real environment signal
181	- [ ] Plan recorded in the transcript as an artifact
182	- [ ] Every irreversible action sandboxed, gated, or absent
183	- [ ] Structured run logs with per-call token counts
184	- [ ] An eval suite that measures task completion, not just "it ran" (`evals-before-shipping`)
185	- [ ] A measured comparison against the workflow you would otherwise have written
186	
187	The last one is the honest test. If the agent does not beat the workflow on your eval set, you have bought latency, cost, and failure modes for nothing — collapse it into the workflow you now know you needed.
188	
[tool_use] Read {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\.claude\\skills\\agent-vs-workflow-decision\\references\\tool-design.md"}
[tool_result] 1	# The Agent-Computer Interface Checklist
2	
3	> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.
4	
5	If you build an agent, the tools *are* the product. Anthropic reports spending more time optimizing the tools than the overall prompt on their SWE-bench agent — the interface between model and environment deserves as much prompt-engineering attention as the system prompt, and usually gets none.
6	
7	This is the checklist with before/after examples. The full treatment — decomposition, `input_examples`, tool search, programmatic calling, and the measurement loop — is the `tool-design` skill.
8	
9	## 1. Descriptions are docstrings for a new engineer
10	
11	The description is fed to the model on every request. Vague descriptions cause misuse, and misuse looks like a model problem.
12	
13	```python
14	# BEFORE
15	{"name": "search", "description": "Search for stuff."}
16	
17	# AFTER
18	{
19	    "name": "search_support_tickets",
20	    "description": (
21	        "Search the support ticket store by text, status, and date range. "
22	        "Returns ticket id, title, status, and opened_at — not the ticket body; "
23	        "use get_ticket for that. Use when the user asks about past issues or "
24	        "patterns across tickets. Do not use for live chat sessions, which are "
25	        "in a different store."
26	    ),
27	}
28	```
29	
30	Cover: what it does, when to use it, **when not to**, what each parameter means, and what it does *not* return. Aim for three or four sentences; more if the tool is complex. The "what it does not return" clause prevents the most common wasted turn — the agent calling the tool, not finding a field, and calling it again with different arguments.
31	
32	## 2. Choose formats the model writes naturally
33	
34	Some output formats require the model to do bookkeeping before it can write a token. That bookkeeping is where errors come from.
35	
36	| Format | Hidden cost |
37	|---|---|
38	| Unified diff | Requires counting line numbers before writing anything |
39	| JSON-wrapped code | Requires escaping quotes, newlines, backslashes correctly |
40	| Markdown / plain text | Neither |
41	
42	Anthropic's finding is concrete: on a text-editor tool, formats that avoid pre-writing bookkeeping produce fewer errors. Prefer `old_string` / `new_string` replacement over line-numbered patches; prefer a raw code block over a JSON string containing code.
43	
44	The general rule: **if the model has to compute something before it can start writing, it will sometimes compute it wrong.**
45	
46	## 3. Leave room to think
47	
48	A format the model cannot back out of, chosen before it has reasoned, is a trap.
49	
50	```python
51	# BEFORE — the first token commits to a path
52	{"properties": {"action": {"enum": ["approve", "deny"]}}}
53	
54	# AFTER — reasoning precedes the commitment
55	{"properties": {
56	    "reasoning": {"type": "string", "description": "Why this decision, citing the policy."},
57	    "action": {"enum": ["approve", "deny", "needs_human"]},
58	}}
59	```
60	
61	Fields generate in order, so a reasoning field declared first is thinking; declared last, it is rationalization. Note `needs_human` as well — a binary choice with no escape hatch forces a decision on cases that deserve neither answer.
62	
63	## 4. Poka-yoke the arguments
64	
65	Make the mistake impossible rather than documenting it.
66	
67	```python
68	# BEFORE — relative paths. The agent must track its own working directory
69	#          across turns, and it sometimes doesn't.
70	{"path": {"type": "string", "description": "Path to the file"}}
71	
72	# AFTER — absolute paths. An entire failure class removed.
73	{"path": {"type": "string",
74	          "description": "Absolute path, e.g. /repo/src/auth.py. Relative paths rejected."}}
75	```
76	
77	Anthropic reports that switching to absolute filepaths removed an entire class of failure in their SWE-bench agent. Look for the same shape elsewhere:
78	
79	- **Enums over free strings** wherever the value set is known. `enum` is one of the few constraints genuinely enforced during generation.
80	- **Explicit units in the parameter name.** `timeout_seconds`, not `timeout`. `amount_usd`, not `amount`.
81	- **Unambiguous names.** `user_id`, not `user` — the latter invites a username.
82	- **Polarity in the tool name**, not in a mode flag, when getting it wrong is silent and damaging. `filter_excluding_value` cannot be inverted the way `mode="exclude"` can. Apply this only where a measurement shows the flag being set wrong; splitting preemptively inflates tool count, which degrades selection on its own.
83	
84	## 5. Return high-signal context
85	
86	Return what informs the next action; drop the rest.
87	
88	```python
89	# BEFORE
90	{"uuid": "8f14e45f-ea", "mime_type": "application/pdf",
91	 "256px_image_url": "...", "created_ts": 1736899200}
92	
93	# AFTER
94	{"name": "Q3-forecast.pdf", "file_type": "pdf", "url": "...",
95	 "created": "2026-01-15"}
96	```
97	
98	**Resolve cryptic identifiers to semantic ones.** Replacing arbitrary UUIDs with meaningful names — or even a 0-indexed scheme — measurably improves retrieval precision and reduces hallucination.
99	
100	When the agent sometimes needs technical IDs for a follow-up call, expose a `response_format` enum (`"concise"` / `"detailed"`) rather than always returning everything. In Anthropic's Slack tooling, `concise` responses used roughly a third the tokens of `detailed` ones.
101	
102	## 6. Errors steer, they do not report
103	
104	An error the agent cannot act on wastes a turn and often triggers a retry of the identical call.
105	
106	```python
107	# BEFORE
108	{"error": "ValidationError: invalid input"}
109	
110	# AFTER
111	{"error": "date_range too large (max 90 days). Retry with a narrower range, "
112	          "e.g. start_date='2026-01-01', end_date='2026-03-01'. For longer "
113	          "spans, call repeatedly and aggregate."}
114	```
115	
116	Same for truncation: say "this result was truncated at 100 rows; narrow the filter or paginate with `offset`," not "…".
117	
118	## 7. Build tools for tasks, not for endpoints
119	
120	Endpoint count is not tool count. Agents have different affordances than programs — context is scarce, so a tool that returns everything and makes the agent scan it wastes the resource that matters.
121	
122	```text
123	list_users + list_events + create_event            →  schedule_event
124	get_customer + list_transactions + list_notes      →  get_customer_context
125	read_logs (returns everything)                     →  search_logs (returns matches)
126	```
127	
128	Each tool should have a clear, distinct purpose matching how a human would subdivide the task. Overlapping tools distract the agent from efficient strategies.
129	
130	## 8. Test with real inputs and iterate
131	
132	Small description changes produce large effects. Claude Sonnet 3.5's SWE-bench Verified result came substantially from precise tool-description refinements. Anthropic also found Claude appending `2025` to web search queries unprompted, degrading results — the fix was a description change, and it was only findable by reading transcripts.
133	
134	The minimum loop:
135	
136	1. Write realistic tasks — ones that need several tool calls and do not name the tool in the prompt. "Customer 9182 reported being charged three times; find the relevant log entries and determine if other customers were affected" is a strong task; "search the payment logs for customer_id=9182" is not.
137	2. Run each in a plain `while` loop against the real API.
138	3. Track tool calls per task, errors by type, tokens, and runtime — not just accuracy.
139	4. **Read the raw transcripts.** What the agent omits from its explanation matters as much as what it says.
140	5. Hold out a test set so you don't overfit descriptions to your examples.
141	
142	Use `evals-before-shipping` for the harness, with tool-correctness and argument-correctness as the primary measures.
143	
144	## The diagnostic table
145	
146	| Symptom | Fix |
147	|---|---|
148	| Wrong tool chosen | Naming, namespacing, removing near-identical names |
149	| Right tool, wrong arguments | `input_examples`, or decomposition if the ambiguity is semantic |
150	| Same tool called repeatedly with no progress | Error text that steers; better return format |
151	| Definitions eating context | Deferred loading plus a tool search tool |
152	| Results eating context | Pagination, filtering, or programmatic tool calling |
153	| Agent ignores a tool entirely | Description doesn't say *when* to use it |
154	
155	Each of these is a remedy for a measured failure, not a default. Write the natural tool first, measure, then apply the one the measurement points to.
156	
[tool_use] Bash {"command": "python3 --version; python --version; pip show anthropic 2>&1 | head -5; echo \"---env---\"; [ -n \"$ANTHROPIC_API_KEY\" ] && echo \"ANTHROPIC_API_KEY is set\" || echo \"ANTHROPIC_API_KEY not set\"", "description": "Check Python/pip availability and whether API key is configured"}
[tool_result] Python was not found; run without arguments to install from the Microsoft Store, or disable this shortcut from Settings > Apps > Advanced app settings > App execution aliases.

Python 3.10.5

Name: anthropic

Version: 1.5.0

Summary: The official Python library for the anthropic API

Home-page: https://github.com/anthropics/anthropic-sdk-python

Author: 

---env---
ANTHROPIC_API_KEY not set
[assistant] Let me check the claude-api reference for exact SDK usage and current model pricing before writing code, so the tool is accurate.
[tool_use] Bash {"command": "find \"C:\\tmp\\skills-eval\\arm-b\\t16-r2\\.claude\\skills\" -iname \"*claude-api*\" 2>/dev/null; echo \"---\"; find / -maxdepth 6 -iname \"claude-api\" -type d 2>/dev/null", "description": "Look for claude-api skill files"}
[tool_result] Command did not complete within its 120s timeout and was moved to the background (ID: bgvv7xpry). Output is being written to: C:\Users\Osama\AppData\Local\Temp\claude\C--tmp-skills-eval-arm-b-t16-r2\d0bde431-6072-490a-aa4d-fde40ddb4150\tasks\bgvv7xpry.output. You will be notified when it completes. To check interim output, use Read on that file path.
[tool_use] Bash {"command": "python -c \"import anthropic, os; print(os.path.dirname(anthropic.__file__))\"", "description": "Find anthropic package install location"}
[tool_result] C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic
[tool_use] Bash {"command": "python - <<'EOF'\nimport anthropic, inspect\nprint(anthropic.__version__)\nsig = inspect.signature(anthropic.resources.messages.Messages.create)\nprint(sig)\nEOF", "description": "Inspect anthropic SDK messages.create signature"}
[tool_result] 1.5.0

(self, *, max_tokens: 'int', messages: 'Iterable[MessageParam]', model: 'ModelParam', cache_control: 'Optional[CacheControlEphemeralParam] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, container: 'Optional[MessageCreateParamsContainerParam] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, inference_geo: 'Optional[str] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, metadata: 'MetadataParam | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, output_config: 'OutputConfigParam | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, service_tier: "Literal['auto', 'standard_only'] | Omit" = <anthropic.Omit object at 0x0000024F77FACB50>, stop_sequences: 'SequenceNotStr[str] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, stream: 'Literal[False] | Literal[True] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, system: 'Union[str, Iterable[TextBlockParam]] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, thinking: 'ThinkingConfigParam | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, tool_choice: 'ToolChoiceParam | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, tools: 'Iterable[ToolUnionParam] | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, user_profile_id: 'str | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, workspace_id: 'str | Omit' = <anthropic.Omit object at 0x0000024F77FACB50>, extra_headers: 'Headers | None' = None, extra_query: 'Query | None' = None, extra_body: 'Body | None' = None, timeout: 'float | httpx2.Timeout | None | NotGiven' = NOT_GIVEN) -> 'Message | Stream[RawMessageStreamEvent]'
[assistant] Good — confirms the standard tool-use API shape (`tools`, `tool_choice`, `system`, `messages`, `output_config.task_budget`). Now I'll write the agent.
[tool_use] Write {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\fix_test.py", "content": "\"\"\"Agent that takes one failing test and iterates (read, edit, run) until it passes.\n\nUsage:\n    python fix_test.py --repo /path/to/repo --test-cmd \"pytest tests/test_foo.py::test_bar -x\"\n\nSee --help for budget caps, model choice, and pricing overrides.\n\"\"\"\nfrom __future__ import annotations\n\nimport argparse\nimport json\nimport re\nimport subprocess\nimport time\nimport uuid\nfrom collections import Counter\nfrom dataclasses import dataclass, field\nfrom pathlib import Path\n\nimport anthropic\n\nMAX_TOOL_OUTPUT_CHARS = 4000\nMAX_SEARCH_MATCHES = 200\n\n\n# ---------------------------------------------------------------------------\n# Budget / run state — see .claude/skills/agent-vs-workflow-decision\n# ---------------------------------------------------------------------------\n\n@dataclass\nclass Budget:\n    max_iterations: int = 15\n    max_cost_usd: float = 2.00\n    max_wall_clock_s: float = 600.0\n    # Placeholder rates — verify against current pricing before relying on the\n    # cost cap; override with --price-in-per-mtok / --price-out-per-mtok.\n    price_in_per_mtok: float = 3.00\n    price_out_per_mtok: float = 15.00\n\n\n@dataclass\nclass RunState:\n    iterations: int = 0\n    cost_usd: float = 0.0\n    started: float = field(default_factory=time.monotonic)\n    call_signatures: Counter = field(default_factory=Counter)\n    tool_call_log: list = field(default_factory=list)\n    plan_revisions: int = 0\n    last_run_tests_passed: bool | None = None\n\n    def elapsed(self) -> float:\n        return time.monotonic() - self.started\n\n\ndef check_budget(state: RunState, budget: Budget) -> str | None:\n    if state.iterations >= budget.max_iterations:\n        return \"max_iterations\"\n    if state.cost_usd >= budget.max_cost_usd:\n        return \"budget_exceeded\"\n    if state.elapsed() >= budget.max_wall_clock_s:\n        return \"timeout\"\n    if max(state.call_signatures.values(), default=0) >= 3:\n        return \"stuck\"\n    return None\n\n\ndef price(usage, budget: Budget) -> float:\n    return (usage.input_tokens / 1e6) * budget.price_in_per_mtok + \\\n           (usage.output_tokens / 1e6) * budget.price_out_per_mtok\n\n\ndef truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:\n    if len(text) <= limit:\n        return text\n    return text[:limit] + f\"\\n...[truncated {len(text) - limit} chars; narrow your request]\"\n\n\n# ---------------------------------------------------------------------------\n# Sandbox: every tool is confined to the repo root, no path traversal out.\n# ---------------------------------------------------------------------------\n\nclass Sandbox:\n    def __init__(self, repo_root: Path):\n        self.root = repo_root.resolve()\n\n    def resolve(self, rel_path: str) -> Path:\n        if Path(rel_path).is_absolute() or \"..\" in Path(rel_path).parts:\n            raise ValueError(\n                f\"path must be relative to the repo root and may not contain '..': {rel_path!r}\"\n            )\n        candidate = (self.root / rel_path).resolve()\n        if self.root not in candidate.parents and candidate != self.root:\n            raise ValueError(f\"path escapes the repo root: {rel_path!r}\")\n        return candidate\n\n\n# ---------------------------------------------------------------------------\n# Tools. Each returns (result_dict, is_error, ground_truth: bool)\n# ---------------------------------------------------------------------------\n\nTOOLS = [\n    {\n        \"name\": \"read_file\",\n        \"description\": (\n            \"Read a text file from the target repo. path is relative to the repo root \"\n            \"(e.g. 'src/util.py') — absolute paths and '..' are rejected. Returns content \"\n            \"with 1-indexed line numbers prefixed, so exact line context is visible for \"\n            \"edit_file calls. Optionally pass start_line/end_line (1-indexed, inclusive) \"\n            \"to read a slice instead of a whole large file.\"\n        ),\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"path\": {\"type\": \"string\"},\n                \"start_line\": {\"type\": \"integer\"},\n                \"end_line\": {\"type\": \"integer\"},\n            },\n            \"required\": [\"path\"],\n            \"additionalProperties\": False,\n        },\n    },\n    {\n        \"name\": \"search_files\",\n        \"description\": (\n            \"Search file contents across the repo for a regex pattern, optionally restricted \"\n            \"to files matching a glob (e.g. '*.py'). Returns matching file paths with line \"\n            \"numbers and line text, capped at 200 matches. Use this to locate where a symbol, \"\n            \"function, or error string is defined before reading a whole file.\"\n        ),\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"pattern\": {\"type\": \"string\"},\n                \"glob\": {\"type\": \"string\"},\n            },\n            \"required\": [\"pattern\"],\n            \"additionalProperties\": False,\n        },\n    },\n    {\n        \"name\": \"edit_file\",\n        \"description\": (\n            \"Replace an exact, unique text match in a file. old_string must match the current \"\n            \"file content exactly, including whitespace, and must appear exactly once — include \"\n            \"enough surrounding context to make it unique. Fails with an error (no partial edit) \"\n            \"if old_string is missing or appears more than once. Always read_file first to see \"\n            \"the exact current content. To insert new content, include an anchor line in both \"\n            \"old_string and new_string.\"\n        ),\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"path\": {\"type\": \"string\"},\n                \"old_string\": {\"type\": \"string\"},\n                \"new_string\": {\"type\": \"string\"},\n            },\n            \"required\": [\"path\", \"old_string\", \"new_string\"],\n            \"additionalProperties\": False,\n        },\n    },\n    {\n        \"name\": \"run_tests\",\n        \"description\": (\n            \"Run the target test command in the repo and report the result. Returns exit_code, \"\n            \"stdout, and stderr (each truncated with a note if long). This is the ground-truth \"\n            \"signal for whether a fix works — call it after every edit you believe might fix the \"\n            \"failure. Never assert the test passes without calling this and reading exit_code.\"\n        ),\n        \"input_schema\": {\"type\": \"object\", \"properties\": {}, \"additionalProperties\": False},\n    },\n    {\n        \"name\": \"record_plan\",\n        \"description\": (\n            \"Record or update your plan before acting, and again whenever it changes materially. \"\n            \"Stored in the run log for human review; does not affect execution.\"\n        ),\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"steps\": {\"type\": \"array\", \"items\": {\"type\": \"string\"}},\n                \"success_criteria\": {\"type\": \"string\"},\n            },\n            \"required\": [\"steps\", \"success_criteria\"],\n            \"additionalProperties\": False,\n        },\n    },\n]\n\n\nclass ToolRunner:\n    def __init__(self, sandbox: Sandbox, test_cmd: str, state: RunState):\n        self.sandbox = sandbox\n        self.test_cmd = test_cmd\n        self.state = state\n\n    def dispatch(self, name: str, args: dict) -> tuple[dict, bool]:\n        try:\n            if name == \"read_file\":\n                return self._read_file(**args), False\n            if name == \"search_files\":\n                return self._search_files(**args), False\n            if name == \"edit_file\":\n                return self._edit_file(**args), False\n            if name == \"run_tests\":\n                return self._run_tests(), False\n            if name == \"record_plan\":\n                self.state.plan_revisions += 1\n                return {\"ok\": True, \"recorded\": args}, False\n            return {\"error\": f\"unknown tool {name}\"}, True\n        except Exception as exc:  # noqa: BLE001 - surfaced to the model as a steerable error\n            return {\"error\": str(exc)}, True\n\n    def _read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> dict:\n        p = self.sandbox.resolve(path)\n        if not p.is_file():\n            return {\"error\": f\"no such file: {path}\"}\n        lines = p.read_text(encoding=\"utf-8\", errors=\"replace\").splitlines()\n        lo = (start_line or 1) - 1\n        hi = end_line or len(lines)\n        numbered = \"\\n\".join(f\"{i + 1}\\t{line}\" for i, line in enumerate(lines[lo:hi], start=lo))\n        return {\"path\": path, \"total_lines\": len(lines), \"content\": truncate(numbered)}\n\n    def _search_files(self, pattern: str, glob: str = \"*\") -> dict:\n        try:\n            rx = re.compile(pattern)\n        except re.error as exc:\n            return {\"error\": f\"invalid regex: {exc}\"}\n        matches = []\n        for fp in self.sandbox.root.rglob(glob):\n            if not fp.is_file() or \".git\" in fp.parts:\n                continue\n            try:\n                text = fp.read_text(encoding=\"utf-8\", errors=\"ignore\")\n            except OSError:\n                continue\n            for i, line in enumerate(text.splitlines(), start=1):\n                if rx.search(line):\n                    matches.append({\n                        \"path\": str(fp.relative_to(self.sandbox.root)).replace(\"\\\\\", \"/\"),\n                        \"line\": i,\n                        \"text\": line.strip()[:200],\n                    })\n                    if len(matches) >= MAX_SEARCH_MATCHES:\n                        return {\"matches\": matches, \"truncated\": True}\n        return {\"matches\": matches, \"truncated\": False}\n\n    def _edit_file(self, path: str, old_string: str, new_string: str) -> dict:\n        p = self.sandbox.resolve(path)\n        if not p.is_file():\n            return {\"error\": f\"no such file: {path}\"}\n        text = p.read_text(encoding=\"utf-8\", errors=\"replace\")\n        count = text.count(old_string)\n        if count == 0:\n            return {\"error\": \"old_string not found — it must match the file exactly, \"\n                              \"including whitespace. Re-read the file to check current content.\"}\n        if count > 1:\n            return {\"error\": f\"old_string is not unique ({count} occurrences) — include more \"\n                              \"surrounding context so it matches exactly one location.\"}\n        p.write_text(text.replace(old_string, new_string, 1), encoding=\"utf-8\")\n        return {\"ok\": True, \"path\": path}\n\n    def _run_tests(self) -> dict:\n        try:\n            proc = subprocess.run(\n                self.test_cmd, shell=True, cwd=self.sandbox.root,\n                capture_output=True, text=True, timeout=120,\n            )\n            passed = proc.returncode == 0\n            self.state.last_run_tests_passed = passed\n            return {\n                \"exit_code\": proc.returncode,\n                \"passed\": passed,\n                \"stdout\": truncate(proc.stdout),\n                \"stderr\": truncate(proc.stderr),\n            }\n        except subprocess.TimeoutExpired:\n            self.state.last_run_tests_passed = False\n            return {\"error\": \"test command timed out after 120s\"}\n\n\n# ---------------------------------------------------------------------------\n# Agent loop\n# ---------------------------------------------------------------------------\n\nSYSTEM_PROMPT = \"\"\"You are fixing one failing test in a real repository. Work autonomously \\\nusing the provided tools until the test passes or you are certain it cannot be fixed within \\\nscope.\n\nProcess:\n1. Call record_plan with your initial investigation plan and success criteria.\n2. Investigate with search_files / read_file before changing anything — understand why the \\\ntest fails, don't guess from the error string alone.\n3. Make the smallest edit_file change that addresses the root cause. Prefer fixing the \\\nimplementation over the test. Only modify the test file itself if you find clear evidence \\\nthe test is wrong (e.g. it contradicts documented behavior) — state that reasoning explicitly \\\nif you do.\n4. Call run_tests after every change that might affect the outcome. Never claim the test \\\npasses without a run_tests call showing passed: true in this turn or the previous one.\n5. If run_tests still fails, read the new stdout/stderr carefully — it usually tells you \\\nexactly what's still wrong — and revise your plan with record_plan if your approach changed.\n6. Once run_tests reports passed: true, stop making tool calls and reply with a short summary \\\nof the root cause and the fix.\n\nIf you get stuck after a genuine attempt, stop and explain what you tried and why it isn't \\\nworking, rather than repeating the same edit.\"\"\"\n\n\ndef run_agent(repo_root: Path, test_cmd: str, budget: Budget, model: str) -> dict:\n    client = anthropic.Anthropic()\n    sandbox = Sandbox(repo_root)\n    state = RunState()\n    runner = ToolRunner(sandbox, test_cmd, state)\n    run_id = str(uuid.uuid4())\n\n    baseline = runner._run_tests()\n    messages = [{\n        \"role\": \"user\",\n        \"content\": (\n            f\"Repo root: {repo_root}\\nTest command: {test_cmd}\\n\\n\"\n            f\"Baseline run_tests result (already executed, do not repeat it as your first \"\n            f\"action):\\n{json.dumps(baseline, indent=2)}\\n\\n\"\n            \"Fix the repo so this test command exits 0.\"\n        ),\n    }]\n\n    status = None\n    while status is None:\n        status = check_budget(state, budget)\n        if status:\n            break\n\n        response = client.messages.create(\n            model=model, max_tokens=4096, system=SYSTEM_PROMPT,\n            tools=TOOLS, messages=messages,\n        )\n        state.iterations += 1\n        state.cost_usd += price(response.usage, budget)\n\n        assistant_content = [block.model_dump() for block in response.content]\n        messages.append({\"role\": \"assistant\", \"content\": assistant_content})\n\n        tool_use_blocks = [b for b in response.content if b.type == \"tool_use\"]\n        if not tool_use_blocks:\n            break  # model is done talking; verify independently below\n\n        status = check_budget(state, budget)  # re-check after paying for this response\n        if status:\n            break\n\n        tool_results = []\n        for tc in tool_use_blocks:\n            sig = (tc.name, json.dumps(tc.input, sort_keys=True))\n            state.call_signatures[sig] += 1\n            if state.call_signatures[sig] == 2:\n                result, is_error = {\n                    \"error\": \"You already called this tool with these exact arguments and got \"\n                             \"this same result. Try different arguments, a different tool, or \"\n                             \"stop and explain what you have.\"\n                }, True\n            else:\n                result, is_error = runner.dispatch(tc.name, tc.input)\n\n            state.tool_call_log.append({\n                \"i\": state.iterations, \"name\": tc.name, \"args\": tc.input,\n                \"ok\": not is_error, \"result_chars\": len(json.dumps(result)),\n            })\n            tool_results.append({\n                \"type\": \"tool_result\", \"tool_use_id\": tc.id,\n                \"content\": json.dumps(result), \"is_error\": is_error,\n            })\n        messages.append({\"role\": \"user\", \"content\": tool_results})\n\n    # Ground truth is our own final check, not the model's claim.\n    final = runner._run_tests()\n    if status is None:\n        status = \"success\" if final[\"passed\"] else \"stopped_without_passing\"\n\n    outcome = {\n        \"run_id\": run_id, \"status\": status, \"test_passed\": final[\"passed\"],\n        \"iterations\": state.iterations, \"cost_usd\": round(state.cost_usd, 4),\n        \"elapsed_s\": round(state.elapsed(), 1), \"plan_revisions\": state.plan_revisions,\n        \"tool_calls\": state.tool_call_log, \"final_run_tests\": final,\n    }\n    return outcome\n\n\ndef main() -> None:\n    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)\n    ap.add_argument(\"--repo\", required=True, type=Path, help=\"repo root to operate in\")\n    ap.add_argument(\"--test-cmd\", required=True, help=\"shell command that runs the failing test, e.g. 'pytest tests/test_foo.py::test_bar -x'\")\n    ap.add_argument(\"--model\", default=\"claude-sonnet-5\")\n    ap.add_argument(\"--max-iterations\", type=int, default=15)\n    ap.add_argument(\"--max-cost-usd\", type=float, default=2.0)\n    ap.add_argument(\"--max-wall-clock-s\", type=float, default=600.0)\n    ap.add_argument(\"--price-in-per-mtok\", type=float, default=3.0, help=\"USD per million input tokens; verify against current pricing\")\n    ap.add_argument(\"--price-out-per-mtok\", type=float, default=15.0, help=\"USD per million output tokens; verify against current pricing\")\n    ap.add_argument(\"--log\", type=Path, default=None, help=\"write the structured run log here (default: <repo>/.fix_test_run.json)\")\n    ap.add_argument(\"--allow-dirty\", action=\"store_true\", help=\"skip the check that the repo is a clean git working tree before editing\")\n    args = ap.parse_args()\n\n    repo_root = args.repo.resolve()\n    if not repo_root.is_dir():\n        raise SystemExit(f\"not a directory: {repo_root}\")\n\n    if not args.allow_dirty:\n        git_dir = repo_root / \".git\"\n        if git_dir.exists():\n            status = subprocess.run(\n                [\"git\", \"status\", \"--porcelain\"], cwd=repo_root,\n                capture_output=True, text=True,\n            )\n            if status.stdout.strip():\n                raise SystemExit(\n                    \"repo has uncommitted changes — commit or stash first so this run's edits \"\n                    \"are cleanly revertable, or pass --allow-dirty to proceed anyway.\"\n                )\n        else:\n            print(f\"warning: {repo_root} is not a git repo, edits will not be easily revertable\")\n\n    budget = Budget(\n        max_iterations=args.max_iterations, max_cost_usd=args.max_cost_usd,\n        max_wall_clock_s=args.max_wall_clock_s,\n        price_in_per_mtok=args.price_in_per_mtok, price_out_per_mtok=args.price_out_per_mtok,\n    )\n\n    outcome = run_agent(repo_root, args.test_cmd, budget, args.model)\n\n    log_path = args.log or (repo_root / \".fix_test_run.json\")\n    log_path.write_text(json.dumps(outcome, indent=2, default=str), encoding=\"utf-8\")\n\n    print(f\"status: {outcome['status']}  test_passed: {outcome['test_passed']}\")\n    print(f\"iterations: {outcome['iterations']}  cost_usd: {outcome['cost_usd']}  elapsed_s: {outcome['elapsed_s']}\")\n    print(f\"run log: {log_path}\")\n    raise SystemExit(0 if outcome[\"test_passed\"] else 1)\n\n\nif __name__ == \"__main__\":\n    main()\n"}
[tool_result] File created successfully at: C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py (file state is current in your context — no need to Read it back)
[tool_use] Bash {"command": "jobs -l 2>/dev/null; echo done", "description": "Check background job status"}
[tool_result] done
[assistant] That earlier `find /` scan finished on its own; ignoring it. Now let me build a small demo repo with a genuinely failing test and exercise the tool's mechanics directly (sandbox, edit_file, run_tests, budget/stuck logic) without needing a live API key.
[tool_use] Bash {"command": "mkdir -p \"C:/tmp/skills-eval/arm-b/t16-r2/demo/src\" \"C:/tmp/skills-eval/arm-b/t16-r2/demo/tests\" && cd \"C:/tmp/skills-eval/arm-b/t16-r2/demo\" && git init -q && python -c \"import pytest\" && echo pytest-ok", "description": "Create demo repo dirs, init git, confirm pytest installed"}
[tool_result] pytest-ok
[tool_use] Write {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\demo\\src\\mathutils.py", "content": "def average(numbers):\n    \"\"\"Return the arithmetic mean of a non-empty list of numbers.\"\"\"\n    total = 0\n    for n in numbers:\n        total = n  # bug: overwrites instead of accumulating\n    return total / len(numbers)\n"}
[tool_result] File created successfully at: C:\tmp\skills-eval\arm-b\t16-r2\demo\src\mathutils.py (file state is current in your context — no need to Read it back)
[tool_use] Write {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\demo\\tests\\test_mathutils.py", "content": "import sys\nfrom pathlib import Path\n\nsys.path.insert(0, str(Path(__file__).resolve().parents[1] / \"src\"))\n\nfrom mathutils import average\n\n\ndef test_average_of_three_numbers():\n    assert average([1, 2, 3]) == 2\n"}
[tool_result] File created successfully at: C:\tmp\skills-eval\arm-b\t16-r2\demo\tests\test_mathutils.py (file state is current in your context — no need to Read it back)
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2/demo\" && git add -A && git commit -q -m \"demo repo with a deliberately buggy average() and a failing test\" && python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q; echo \"exit=$?\"", "description": "Commit demo repo and confirm the test fails"}
[tool_result] warning: in the working copy of 'src/mathutils.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'tests/test_mathutils.py', LF will be replaced by CRLF the next time Git touches it
F                                                                        [100%]

================================== FAILURES ===================================

________________________ test_average_of_three_numbers ________________________



    def test_average_of_three_numbers():

>       assert average([1, 2, 3]) == 2

E       assert 1.0 == 2

E        +  where 1.0 = average([1, 2, 3])



tests\test_mathutils.py:10: AssertionError

=========================== short test summary info ===========================

FAILED tests/test_mathutils.py::test_average_of_three_numbers - assert 1.0 == 2

1 failed in 0.81s

exit=1
[assistant] Good, the demo repo has a genuinely failing test on a clean git commit. Now let's exercise the tool's harness logic directly (sandbox, edit_file, run_tests, budget/stuck detection) without needing an API key, by driving `ToolRunner` and `check_budget` programmatically.
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2\" && python - <<'EOF'\nfrom pathlib import Path\nimport fix_test as ft\n\nrepo = Path(\"demo\").resolve()\nsandbox = ft.Sandbox(repo)\nstate = ft.RunState()\nrunner = ft.ToolRunner(sandbox, \"python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q\", state)\n\n# 1. sandbox escape rejected\ntry:\n    sandbox.resolve(\"../fix_test.py\")\n    print(\"FAIL: traversal not blocked\")\nexcept ValueError as e:\n    print(\"OK traversal blocked:\", e)\n\n# 2. read_file with line numbers\nr, err = runner.dispatch(\"read_file\", {\"path\": \"src/mathutils.py\"})\nprint(\"read_file err:\", err)\nprint(r[\"content\"])\n\n# 3. baseline run_tests (ground truth) fails\nr, err = runner.dispatch(\"run_tests\", {})\nprint(\"baseline passed:\", r[\"passed\"], \"exit_code:\", r[\"exit_code\"])\n\n# 4. edit_file with non-unique old_string -> should error, not silently pick one\nr, err = runner.dispatch(\"edit_file\", {\"path\": \"src/mathutils.py\", \"old_string\": \"    \", \"new_string\": \"x\"})\nprint(\"non-unique edit err:\", err, r)\n\n# 5. real fix via edit_file (old_string/new_string, no diff bookkeeping)\nr, err = runner.dispatch(\"edit_file\", {\n    \"path\": \"src/mathutils.py\",\n    \"old_string\": \"        total = n  # bug: overwrites instead of accumulating\",\n    \"new_string\": \"        total += n\",\n})\nprint(\"fix edit err:\", err, r)\n\n# 6. run_tests again -> ground truth now passes\nr, err = runner.dispatch(\"run_tests\", {})\nprint(\"after fix passed:\", r[\"passed\"], \"exit_code:\", r[\"exit_code\"])\n\n# 7. stuck detection: same tool+args 3x trips check_budget\nbudget = ft.Budget(max_iterations=100, max_cost_usd=100, max_wall_clock_s=100)\nsig = (\"read_file\", '{\"path\": \"src/mathutils.py\"}')\nstate.call_signatures[sig] = 3\nprint(\"stuck status:\", ft.check_budget(state, budget))\n\n# 8. iteration cap\nstate2 = ft.RunState()\nbudget2 = ft.Budget(max_iterations=2)\nstate2.iterations = 2\nprint(\"iter cap status:\", ft.check_budget(state2, budget2))\nEOF", "description": "Exercise sandbox, tool dispatch, edit/run_tests, and stopping-condition logic directly"}
[tool_result] OK traversal blocked: path must be relative to the repo root and may not contain '..': '../fix_test.py'

read_file err: False

1	def average(numbers):

2	    """Return the arithmetic mean of a non-empty list of numbers."""

3	    total = 0

4	    for n in numbers:

5	        total = n  # bug: overwrites instead of accumulating

6	    return total / len(numbers)

baseline passed: False exit_code: 1

non-unique edit err: False {'error': 'old_string is not unique (6 occurrences) — include more surrounding context so it matches exactly one location.'}

fix edit err: False {'ok': True, 'path': 'src/mathutils.py'}

after fix passed: True exit_code: 0

stuck status: stuck

iter cap status: max_iterations
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2/demo\" && git checkout -- src/mathutils.py && git status --porcelain && echo \"clean, still buggy:\" && grep -n \"total\" src/mathutils.py", "description": "Reset demo repo back to its original failing state"}
[tool_result] ?? src/__pycache__/
?? tests/__pycache__/
clean, still buggy:
3:    total = 0
5:        total = n  # bug: overwrites instead of accumulating
6:    return total / len(numbers)
[tool_use] Write {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\demo\\.gitignore", "content": "__pycache__/\n.fix_test_run.json\n"}
[tool_result] File created successfully at: C:\tmp\skills-eval\arm-b\t16-r2\demo\.gitignore (file state is current in your context — no need to Read it back)
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2/demo\" && rm -rf src/__pycache__ tests/__pycache__ && git add -A && git commit -q -m \"add gitignore\" && git status --porcelain && echo \"---now test CLI dirty-guard on a dirty repo---\" && cd .. && touch demo/scratch.txt && python fix_test.py --repo demo --test-cmd \"python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q\"; echo \"exit=$?\"; rm -f demo/scratch.txt", "description": "Commit gitignore, verify clean status, and confirm CLI refuses to run on a dirty repo"}
[tool_result] warning: in the working copy of '.gitignore', LF will be replaced by CRLF the next time Git touches it
---now test CLI dirty-guard on a dirty repo---
repo has uncommitted changes — commit or stash first so this run's edits are cleanly revertable, or pass --allow-dirty to proceed anyway.

exit=1
[assistant] The dirty-repo guardrail works. Now let's confirm the clean path proceeds to the actual agent loop (expected to fail cleanly on missing API auth, since none is configured here).
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2\" && python fix_test.py --repo demo --test-cmd \"python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q\"; echo \"exit=$?\"", "description": "Run the CLI end-to-end against the demo repo (expect a clean auth error, no API key configured)"}
[tool_result] Traceback (most recent call last):

  File "C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py", line 438, in <module>

    main()

  File "C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py", line 426, in main

    outcome = run_agent(repo_root, args.test_cmd, budget, args.model)

  File "C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py", line 332, in run_agent

    response = client.messages.create(

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_utils\_utils.py", line 294, in wrapper

    return func(*args, **kwargs)

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\resources\messages\messages.py", line 978, in create

    return self._post(

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_base_client.py", line 1509, in post

    return cast(ResponseT, self.request(cast_to, opts, stream=stream, stream_cls=stream_cls))

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_base_client.py", line 1135, in request

    response, prepared = self._attempt_request(

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_base_client.py", line 1275, in _attempt_request

    request = self._build_request(options, retries_taken=retries_taken)

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_base_client.py", line 542, in _build_request

    headers = self._build_headers(options, retries_taken=retries_taken)

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_base_client.py", line 489, in _build_headers

    self._validate_headers(headers, omitted)

  File "C:\Users\Osama\AppData\Local\Programs\Python\Python310\lib\site-packages\anthropic\_client.py", line 409, in _validate_headers

    raise TypeError(

TypeError: "Could not resolve authentication method. Expected one of api_key, auth_token, or credentials to be set. Or for one of the `X-Api-Key` or `Authorization` headers to be explicitly omitted"

exit=1
[tool_use] Edit {"replace_all": false, "file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\fix_test.py", "old_string": "import anthropic\n\nMAX_TOOL_OUTPUT_CHARS = 4000", "new_string": "import os\n\nimport anthropic\n\nMAX_TOOL_OUTPUT_CHARS = 4000"}
[tool_result] The file C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py has been updated successfully. (file state is current in your context — no need to Read it back)
[tool_use] Edit {"replace_all": false, "file_path": "C:\\tmp\\skills-eval\\arm-b\\t16-r2\\fix_test.py", "old_string": "    repo_root = args.repo.resolve()\n    if not repo_root.is_dir():\n        raise SystemExit(f\"not a directory: {repo_root}\")", "new_string": "    if not os.environ.get(\"ANTHROPIC_API_KEY\"):\n        raise SystemExit(\"ANTHROPIC_API_KEY is not set — export it before running this tool.\")\n\n    repo_root = args.repo.resolve()\n    if not repo_root.is_dir():\n        raise SystemExit(f\"not a directory: {repo_root}\")"}
[tool_result] The file C:\tmp\skills-eval\arm-b\t16-r2\fix_test.py has been updated successfully. (file state is current in your context — no need to Read it back)
[assistant] Let's re-verify this fails cleanly now, and also confirm `--help` output is sane.
[tool_use] Bash {"command": "cd \"C:/tmp/skills-eval/arm-b/t16-r2\" && python fix_test.py --repo demo --test-cmd \"x\"; echo \"exit=$?\"; echo \"---help---\"; python fix_test.py --help", "description": "Verify clean missing-API-key error and check --help output"}
[tool_result] ANTHROPIC_API_KEY is not set — export it before running this tool.

exit=1
---help---
usage: fix_test.py [-h] --repo REPO --test-cmd TEST_CMD [--model MODEL]

                   [--max-iterations MAX_ITERATIONS]

                   [--max-cost-usd MAX_COST_USD]

                   [--max-wall-clock-s MAX_WALL_CLOCK_S]

                   [--price-in-per-mtok PRICE_IN_PER_MTOK]

                   [--price-out-per-mtok PRICE_OUT_PER_MTOK] [--log LOG]

                   [--allow-dirty]



Agent that takes one failing test and iterates (read, edit, run) until it passes.



Usage:

    python fix_test.py --repo /path/to/repo --test-cmd "pytest tests/test_foo.py::test_bar -x"



See --help for budget caps, model choice, and pricing overrides.



options:

  -h, --help            show this help message and exit

  --repo REPO           repo root to operate in

  --test-cmd TEST_CMD   shell command that runs the failing test, e.g. 'pytest

                        tests/test_foo.py::test_bar -x'

  --model MODEL

  --max-iterations MAX_ITERATIONS

  --max-cost-usd MAX_COST_USD

  --max-wall-clock-s MAX_WALL_CLOCK_S

  --price-in-per-mtok PRICE_IN_PER_MTOK

                        USD per million input tokens; verify against current

                        pricing

  --price-out-per-mtok PRICE_OUT_PER_MTOK

                        USD per million output tokens; verify against current

                        pricing

  --log LOG             write the structured run log here (default:

                        <repo>/.fix_test_run.json)

  --allow-dirty         skip the check that the repo is a clean git working

                        tree before editing
[assistant] Everything checks out. Here's what I built:

**`fix_test.py`** — an agent (not a workflow: the number of edit/test cycles a failing test needs is genuinely unpredictable, and pytest/the test command give real ground truth at every step, so per `agent-vs-workflow-decision` this clears the bar for a loop rather than a fixed script).

It takes `--repo` and `--test-cmd`, gives the model four tools (`read_file`, `search_files`, `edit_file` with unique old/new-string replacement, `run_tests`) plus a `record_plan` tool for visible planning, and loops until the test passes or a stopping condition trips:

- iteration cap, cost cap, wall-clock cap, and stuck-detection (same tool+args 3x) — all four, checked both before and after paying for each response
- edits are sandboxed to the repo root (path-traversal rejected)
- refuses to run on a dirty git tree unless `--allow-dirty`, so every change is trivially revertable
- pass/fail is decided by the harness's own final `run_tests` call, never by the model's say-so
- writes a structured JSON run log (iterations, cost, tool calls, plan revisions, final result)

I verified the mechanics directly (no API key is configured in this environment, so I couldn't run a live model loop): built a demo repo at `demo/` with a real bug (`average()` overwrites instead of accumulating) and a failing test, then drove the tool functions directly — traversal-blocking, ambiguous-edit rejection, the actual fix via `edit_file`, `run_tests` going from fail→pass, and both the stuck and iteration-cap stopping conditions all behaved correctly. I reset `demo/` back to its original failing state (committed, clean tree) so it's ready for a real run.

To actually use it: `export ANTHROPIC_API_KEY=...` then `python fix_test.py --repo demo --test-cmd "python -m pytest tests/test_mathutils.py::test_average_of_three_numbers -q"`. The pricing constants (`--price-in-per-mtok`/`--price-out-per-mtok`) are placeholders — worth checking current rates before relying on the cost cap.