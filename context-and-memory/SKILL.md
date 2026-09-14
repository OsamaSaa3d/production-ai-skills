---
name: context-and-memory
description: Use this skill when a conversation or agent loop outgrows its context window, or when an agent needs to remember something across a context reset or between sessions. Use it when an agent forgets decisions made earlier in a long task, redoes work it already did, wraps up early because it thinks it is running out of tokens, re-asks what the user already answered, or should be learning a user's preferences and conventions over time. Use it when building compaction, tool-result clearing, a sliding window, a fresh-window handoff, a fact store, a consolidation pass, a self-updating learned-rules markdown file, or a memory tool handler. Covers the four memory types — working, episodic, semantic, procedural — and which one you actually need.
---

# Context and Memory

## Core principle

The context window is working memory: fast, complete, and gone at the end of the task. Everything else is a decision about what survives that boundary and in what form.

> **An episode is not a fact, and a log is not a memory. Something has to perform the reduction — and if nothing does, you have storage, not memory.**

Two consequences run through everything below. First, **every strategy here is lossy or expensive, usually both**, so reach for them in cost order rather than starting with the most sophisticated one. Second, **the failure modes are silent.** A bad compaction, an over-retrieved episode, and a wrong learned rule all look like "the agent is unreliable" 30 turns later, with nothing in the logs pointing back at the cause.

## When to use this skill

- A long-running task runs out of context, or wraps up early because the model is watching its token budget
- The agent contradicts, re-litigates, or redoes something decided before a compaction boundary
- You are choosing between compaction, clearing, a fresh window, or subagents
- Someone proposes "just drop the oldest messages"
- An agent should remember user preferences, project conventions, or environment facts across sessions
- You are building a fact store, a consolidation pass, or wiring a memory tool
- You want the agent to write its own rules into a markdown file — `AGENTS.md`, `CLAUDE.md`, or a learned-rules file
- Memory exists but retrieval pulls in the wrong things, or pulls in everything

Writing or debugging the system prompt itself is `system-prompt-engineering`.

## The four types, and which one you need

The CoALA taxonomy, now the field default. Naming them prevents the standard mistake: building one store and calling it "memory."

| Type | Answers | Lives in | The mistake |
|---|---|---|---|
| **Working** | What am I doing right now? | Context window plus the loop's scratchpad | Treating it as free; it is the only one you pay for on every request |
| **Episodic** | What happened before? | Transcripts, traces, conversation logs | Cheap to write, so it grows without bound and gets over-retrieved |
| **Semantic** | What is true? | A distilled fact/preference store | **Cannot be logged, only distilled** — the step most systems skip |
| **Procedural** | How do I do this here? | System prompt, tool definitions, skills, a markdown file | Overlaps three other places; nobody prunes it |

Most teams need far less than they build. **Start by asking which type the observed failure is.** An agent that forgets a decision from earlier in the same task has a working-memory problem and needs a context strategy, not a vector store. An agent that re-asks the user's timezone every session needs three lines of semantic memory, not a transcript archive.

## Managing the window: four strategies, in cost order

| Strategy | Removes | Cost | Reach for it when |
|---|---|---|---|
| **1. Tool-result clearing** | Raw tool payloads | Cache invalidation at the clear point | Heavy tool use; results are large and already processed |
| **2. Compaction** | Everything, replaced by a summary | Silent information loss | Long back-and-forth needing conversational continuity |
| **3. Fresh window** | Everything | Startup cost re-establishing state | State is recoverable from the filesystem or git |
| **4. Subagents** | Nothing from the parent — the work never enters it | Tokens, coordination failure modes | Exploration whose intermediate steps don't matter |

**1. Tool-result clearing is the right first move.** Once a tool result has been processed, the raw payload rarely needs to stay. On the Claude API this is a server-side context edit (`clear_tool_uses_20250919`) taking a `trigger` threshold, a `keep` count of recent tool uses, and `clear_at_least` to guarantee each clear removes enough tokens to be worth the cache invalidation it causes. The sibling strategy for thinking blocks inverts the cache tradeoff — keeping them preserves the cache, clearing them invalidates it.

**2. Compaction** passes the history back to the model to compress, preserving architectural decisions, unresolved bugs, and implementation details while discarding redundant tool output, then continues with that summary plus the most recently touched files. The whole difficulty is what to drop, so **tune the compaction prompt on real agent traces — maximize recall first, then trim for precision.** Doing it in the other order produces a prompt that reads well and silently drops the constraint that mattered.

**3. A fresh window** sometimes beats a lossy summary, because current models are very good at rediscovering state from a filesystem. Be prescriptive about the startup ritual: confirm the working directory, read `progress.txt` and `tests.json`, read the git log, run one integration test before writing code. Set this up in the *first* window — have the agent write `init.sh`, keep test state in a structured file, and use git commits as checkpoints.

**4. Subagents** burn tens of thousands of tokens exploring and return a 1,000–2,000 token distillation; the search context never enters the parent transcript. Good for retrieval and breadth-first exploration, bad for interdependent subtasks. See `subagents-and-multi-agent`.

**A naive sliding window is almost always the wrong answer.** Dropping the oldest N turns discards the task definition and the early decisions — the highest-value tokens present — and truncating from the front invalidates your cache prefix every turn. Defensible for stateless chat and very little else.

### Tell the agent which one is running

Models that track their remaining token budget will otherwise start wrapping up work as they approach the limit. This looks like laziness and is actually reasonable behavior under a wrong assumption:

```text
Your context window will be automatically compacted as it approaches its limit,
allowing you to continue working from where you left off. Do not stop tasks early
due to token budget concerns. As you approach the limit, save your current progress
and state to memory before the context refreshes.
```

State the inverse when it's true: if compaction is *not* enabled, the agent should be told to checkpoint aggressively instead.

Configuration, compaction-prompt tuning, the fresh-window ritual, and what to measure: [references/context-management.md](references/context-management.md).

## Semantic memory: distilled, not logged

**Logging a transcript is not semantic memory.** An episode goes in; a claim has to come out; something must perform that reduction — an async consolidation pass, or an agent tool that promotes an observation to a durable fact. If nothing does, the store fills with episodes and gets called semantic because the embeddings are.

Run consolidation out of band, not in the hot path. Three things make it work:

- **Bless the empty answer explicitly.** Without a line saying "returning nothing is the correct answer most of the time," the model finds three facts in every session and the store fills with noise.
- **Every claim carries its evidence.** You need it to adjudicate contradictions, and to justify deletion later.
- **Deduplicate and reconcile on write.** A new claim contradicting an existing one is a decision, not an append. Newer usually wins — log the supersession.

**Don't dump memory into context.** Memory that is always loaded is just a longer system prompt with all the attention-budget and cache costs. Retrieve semantic facts by relevance to the current request (a retrieval problem — see `rag-pipeline-standard`); retrieve episodes rarely, preferring a summary of a past session over its transcript. Procedural memory is the one case where always-loaded is often right, because it shapes every action — which is exactly why it must stay small.

## Procedural memory: the agent writing its own rules

This is the pattern people usually mean by "let the agent learn": give it a markdown file it can write to, so it accumulates what it discovers about the user, the project, and the conventions — a `CLAUDE.md` that updates itself.

It works, and **it is a self-modifying system prompt.** A wrong rule learned from one bad session then shapes every future session, invisibly, and nothing in the transcript points at it.

### The gate that makes it safe

Split writable from loaded. The agent proposes; a human promotes.

```text
learned/candidates.md   ← agent-writable, append-only. One entry per observation:
                          date, what happened, proposed rule, evidence.
AGENTS.md / CLAUDE.md   ← human-reviewed, loaded every request. Promotion requires
                          a diff review AND an eval case that fails without the rule.
```

A candidate is promoted only if all four hold:

1. **It recurred.** One occurrence is an incident, not a rule.
2. **It isn't already covered** by an existing rule, a tool description, or the model's defaults.
3. **It cannot be enforced mechanically instead.** See below.
4. **There is an eval case that fails without it.**

Criterion 4 is the one people skip, and it is the one that lets you ever delete the rule again. Without it, every line might be load-bearing, none can be tested, and the instruction file becomes a graveyard.

**What belongs in the file: observations, not inferences.** "The user asked twice for tests to be written before the implementation" is an observation. "The user values TDD" is an inference that will be wrong about a case you haven't seen. Record stated preferences, corrections the user made, environment facts, and constraints discovered the hard way — not personality read from three interactions.

### Prefer a hook to a learned instruction

Instructions are advisory; the model chooses whether to follow them. Hooks run regardless.

| Rule | Belongs in |
|---|---|
| Run the formatter after every edit | A hook or pre-commit |
| Never commit without tests passing | A hook or CI |
| Regenerate types after a migration | A build step, or a path-scoped hook |
| Don't touch `vendor/` | Permissions config |
| Prefer composition over inheritance here | An instruction — it needs judgment |

**If a deterministic check can decide it, don't ask the model.** Moving a rule into a hook gets 100% compliance and costs zero instruction budget.

File format, the user-preference case, contradiction handling, and review cadence: [references/learned-rules.md](references/learned-rules.md).

## If you use a hosted memory tool

Anthropic's memory tool is client-side: the model requests file operations under `/memories`, and **your handler executes them against storage you control.** Two consequences.

The API already injects a memory protocol into the system prompt when the tool is present, so writing your own copy means maintaining a duplicate of a string you don't own. What is worth steering in your own prompt is *scope* ("only record information relevant to X"), not mechanism.

And every file operation is yours to secure. Validate that every path resolves inside the memory root — canonical form plus `relative_to()`, not string matching, because `../`, `..\\`, and `%2e%2e%2f` all have to fail. Reject `delete` and `rename` on the root itself, cap file sizes and `view` output, expire stale files, and strip sensitive data before writing. Models usually refuse to write secrets to memory; "usually" is not something to build on.

**Memory content is untrusted input.** Memory files are written by a process that reads tool output and user text, so anything in them can carry an injection. Treat retrieved memory as data with the same suspicion as any tool result — never as instructions. See `system-prompt-engineering` for trust boundaries.

Handler sketch, consolidation prompt, retrieval policy, and the four types in practice: [references/memory.md](references/memory.md).

## Pitfalls

**Reaching for a vector store when the problem is working memory.** An agent that forgets a decision from earlier in the same task needs a context strategy, not a database.

**A naive sliding window.** Drops the task definition and invalidates the cache prefix every turn.

**Compaction tuned on toy conversations.** Tune on real traces, recall first then precision. Aggressive compaction fails silently and the damage surfaces 30 turns later, when the agent redoes work or violates a constraint nobody can trace.

**Not telling the agent compaction exists.** A context-aware model that doesn't know it will wrap up work early to avoid running out.

**Clearing too eagerly.** Each clear invalidates the cached prefix from that point on. Many small clears cost more in cache writes than they save in input tokens — set `clear_at_least` deliberately.

**Calling a transcript log "semantic memory."** Episodes must be distilled into claims by something. If nothing does it, you have logs.

**A fact store with no expiry or contradiction handling.** Append-only eventually contains both "the user prefers tabs" and "the user prefers spaces," and retrieval picks one at random.

**Memory as a substitute for state.** Task status, test results, and progress belong in structured files and git, not in a fuzzy fact store. Memory is for what you learned, not for where you are.

**Always-loading memory.** That is just a longer system prompt, billed on every request. Retrieve selectively; keep only procedural memory resident.

**Letting the agent promote its own rules.** Agent-authored procedural memory is a self-modifying system prompt. Gate promotion behind a diff review and an eval case.

**Recording inferences as facts.** "The user values clean architecture" is a personality read from three interactions. Record what was said and what happened.

**Rules that should have been hooks.** Anything that must *always* hold belongs in a formatter, a test, or a pre-commit hook, not a politely-worded instruction.

**Trusting memory content as instructions.** It is written by a process that reads untrusted input.

## When to break the rules

- **Stateless, single-turn chat.** A sliding window is fine, there is nothing to compact, and a memory store is overhead for a product nobody returns to.
- **Regulated domains.** Where every claim about a user must be auditable and deletable on request, an opaque distilled fact store is a liability. Keep memory explicit, attributed, and per-user erasable — or don't keep it.
- **Short tasks with a fixed budget.** If the task reliably fits in the window, every strategy here is a cost with no benefit. Measure before building any of it.
- **Prototyping.** Load everything and find out what the agent actually reaches for, then build the retrieval policy against observed usage.

## References

- [references/context-management.md](references/context-management.md) — tool-result and thinking clearing, compaction-prompt tuning, fresh-window ritual, multi-window handoff, metrics
- [references/memory.md](references/memory.md) — the four types in practice, consolidation prompt, memory-tool handler and its security, retrieval policy
- [references/learned-rules.md](references/learned-rules.md) — the self-updating markdown file: entry format, observation vs inference, promotion gate, contradiction handling, pruning cadence
