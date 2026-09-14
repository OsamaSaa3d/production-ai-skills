# Context Management

Four strategies, in the order you should reach for them. Each trades something different; none is free.

| Strategy | Removes | Cost | Reach for it when |
|---|---|---|---|
| Tool-result clearing | Raw tool payloads | Cache invalidation at the clear point | Heavy tool use; results are large and already processed |
| Compaction | Everything, replaced by a summary | Silent information loss | Long back-and-forth needing conversational continuity |
| Fresh window | Everything | Startup cost re-establishing state | State is recoverable from the filesystem or git |
| Subagents | Nothing from the parent — the work never enters it | Tokens, coordination failure modes | Exploration whose intermediate steps don't matter |

**A naive sliding window is not on this list.** Dropping the oldest N turns discards the task definition and the early decisions — usually the highest-value tokens present — and truncating from the front invalidates the cache prefix every turn. It's defensible for stateless chat and little else.

## 1. Tool-result clearing

The lightest-touch option and the right first move. Once a tool result has been processed, the raw payload rarely needs to remain — a file you read 40 turns ago, a search result you already extracted from.

```python
resp = client.beta.messages.create(
    model=MODEL,
    max_tokens=4096,
    tools=TOOLS,
    system=SYSTEM,
    messages=messages,
    context_management={
        "edits": [
            {
                "type": "clear_tool_uses_20250919",
                # start clearing once context exceeds this
                "trigger": {"type": "input_tokens", "value": 30_000},
                # how many recent tool uses survive
                "keep": {"type": "tool_uses", "value": 3},
                # guarantee each clear is worth the cache write
                "clear_at_least": {"type": "input_tokens", "value": 5_000},
            }
        ]
    },
)
```

Applied server-side before the prompt reaches the model. Set `clear_at_least` deliberately: each clear invalidates the cached prefix from the clear point onward, so many small clears cost more in cache writes than they save in input tokens.

**Thinking-block clearing** (`clear_thinking_20251015`) is the sibling strategy. The tradeoff is inverted: keeping thinking blocks *preserves* the cache; clearing them invalidates at the clear point. Defaults are model-specific — some models keep all turns, older ones keep only the last — so if your code spans model tiers, set `keep` explicitly rather than inheriting a default that differs per model.

## 2. Compaction

Summarize the conversation as it nears the limit and reinitialize with the summary. The standard first lever for long-horizon coherence.

What Claude Code preserves and drops, as a starting template:

```text
KEEP:
  - architectural and design decisions, with the reasoning
  - unresolved bugs and their symptoms
  - implementation details of what has been built
  - the current goal and what remains
  - constraints discovered the hard way ("the test suite needs X running first")

DROP:
  - raw tool outputs already acted on
  - superseded plans
  - restatements and acknowledgements
  - exploration that led nowhere, beyond one line recording that it did
```

Then continue with the summary plus the handful of most recently accessed files.

**Tune the compaction prompt on real agent traces, recall first.** Start by making sure it captures every relevant piece of information from a trace — accept that it's verbose. Only then iterate on precision by cutting superfluous content. Doing it in the other order produces a compaction prompt that reads well and silently drops the constraint that mattered.

**The failure mode is invisible.** Over-aggressive compaction loses subtle context whose importance only becomes apparent 30 turns later, when the agent redoes work or violates a constraint nobody can trace. Test by running a long task with compaction and checking whether decisions made before the compaction boundary are still respected after it.

## 3. A fresh window instead of compaction

Current models are strong at rediscovering state from a filesystem, which is sometimes better than a lossy summary. If you take this route, be prescriptive about the startup ritual:

```text
Start by orienting yourself:
1. Run pwd. You can only read and write files in this directory.
2. Read progress.txt, tests.json, and the last 20 lines of git log.
3. Run ./init.sh to start the services and confirm the suite runs.
4. Run one fundamental integration test before implementing anything new.
Then continue from the first unfinished item in tests.json.
```

Structural things that make this work, worth setting up in the *first* context window:

- **Use a different prompt for the first window.** Spend it building the framework — write the tests, create the setup scripts — then let later windows iterate against a to-do list.
- **Keep test state in a structured file** (`tests.json` with id, name, status). Structure helps the model understand the schema; freeform notes are better for progress narrative.
- **Add "it is unacceptable to remove or edit tests"** if you see tests being deleted to make things pass.
- **Have the agent write `init.sh`** so each fresh window doesn't rediscover how to start the services.
- **Use git as the state log.** Commits are checkpoints and the log is a summary the agent didn't have to write.

## 4. Subagents

A subagent explores with its own context window and returns a distillation — typically 1,000-2,000 tokens from tens of thousands consumed. The detailed search context never enters the parent transcript.

Best fit: retrieval, codebase exploration, and breadth-first research where the intermediate steps genuinely don't need to influence the parent's reasoning. Poor fit: anything where subtasks are interdependent. See `subagents-and-multi-agent` for the independence test and cost multipliers.

## Tell the agent what's running

Models that track their remaining token budget will otherwise start wrapping up work as they approach the limit — reasonable behavior that looks like laziness.

```text
Your context window will be automatically compacted as it approaches its
limit, allowing you to continue working from where you left off. Do not stop
tasks early due to token budget concerns. As you approach the limit, save your
current progress and state to memory before the context refreshes. Never
artificially stop a task early because of remaining context.
```

The inverse also needs stating when it's true. If compaction is *not* enabled, the agent should be told to checkpoint aggressively instead.

For long tasks where the budget should be spent rather than conserved:

```text
This is a long task, so plan your work clearly. It's encouraged to spend your
entire output context on it — just don't run out with significant uncommitted
work. Continue working systematically until it's complete.
```

## Measuring whether any of it worked

Track per run:

- tokens at each turn, and the number of compaction or clearing events
- **post-boundary constraint violations**: decisions made before a compaction that were contradicted after it
- repeated work: the same file read or the same test run twice on either side of a boundary
- cache hit rate (clearing and compaction both invalidate; make sure the savings are net positive)

The second metric is the one that catches bad compaction, and it's the one nobody instruments.
