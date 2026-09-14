# Behavior Knobs

Paste-able blocks for the symptom table in `SKILL.md`. **One knob per observed symptom, measured after.** Pasting the whole file into a prompt is the failure mode this file exists to prevent — several of these contradict each other, which is the point: they are corrections in opposite directions.

Before reaching for any of them, check the two escape routes:

1. **Is there an API parameter?** Verbosity, reasoning effort, and thinking depth are parameters on current models. Zero tokens per request, cannot contradict anything, cannot drift.
2. **Is this a documented default of the model you're running?** Fighting a documented tendency with untested prose usually suppresses something you wanted.

To calibrate expectations: OpenAI reports that adding persistence, tool-grounding, and planning reminders raised their internal SWE-bench Verified score by close to 20%, with explicit planning alone worth about 4%. Large for three paragraphs — and measured on one model and one task, so treat it as evidence the category matters, not as your expected delta.

---

## Solution persistence

**Symptom:** stops mid-task, hands back partial work, asks a question instead of acting.

```text
You are an agent — keep going until the user's request is completely resolved
before ending your turn. Only stop when you are sure the problem is solved.

Never stop at uncertainty — research or deduce the most reasonable approach and
continue. Do not ask the human to confirm assumptions you can test yourself;
decide, act, document the assumption, and adjust after.
```

**Escape hatch it needs:** this block will also make the agent push through decisions it genuinely should not make alone. Pair it with an explicit list of what does require confirmation (see *Reversibility* below), or it will act on ambiguity that matters.

## Tool grounding

**Symptom:** guesses at file contents, invents function signatures, describes code structure it never opened.

```text
If you are not sure about file content or codebase structure pertaining to the
user's request, use your tools to read files and gather the relevant information.
Do NOT guess or make up an answer.
```

Short, and one of the highest-yield blocks there is. The failure it fixes is confident fabrication, which is the expensive kind.

## Planning and reflection

**Symptom:** chains tool calls with no visible reasoning; the trace is a wall of calls and you cannot tell why any of them happened.

```text
You must plan extensively before each function call, and reflect extensively on
the outcomes of the previous function calls. Do not do this entire process by
making function calls only — it degrades your ability to think insightfully.
```

For models with native thinking, prefer the reasoning-effort parameter first; this block is for models without it, or for forcing reflection *between* calls rather than only at the start.

## User updates during long work

**Symptom:** silent for long stretches during a rollout; the user cannot tell whether it is working or stuck.

Be specific about frequency, length, and content — a vague "keep the user informed" produces either nothing or a running commentary.

```text
Before making tool calls, send a brief message to the user explaining what you
are about to do and why. Keep these to 1-2 sentences.

During long tasks, post a progress update roughly every 3-5 tool calls: what you
finished, what you found, what is next. Do not narrate individual file reads.
```

## Length keyed to task size

**Symptom:** uniformly too verbose or too terse.

Try the verbosity parameter first. If prose is still needed, key it to task size rather than stating an absolute — an absolute will contradict something else in the prompt:

```text
Match response length to request complexity:
- Single-topic question, or a change under ~10 lines: 3-6 sentences, no headings.
- Multi-file change or a plan: structured sections are appropriate.
Do not add a summary section to a response that is already under a page.
```

## Scope minimalism

**Symptom:** extra files, speculative abstractions, unrequested refactors, a README nobody asked for.

```text
Do only what was asked. Prefer editing an existing file to creating a new one.
Do not create documentation files unless explicitly requested. Do not refactor
code adjacent to your change unless the change requires it.

If you believe additional work is warranted, say so in one sentence and let the
user decide.
```

That last paragraph matters — without it the model either over-reaches or silently drops a real concern.

## Investigate before answering

**Symptom:** claims about behavior, performance, or intent of code it never read.

```text
Before making a claim about how this codebase behaves, read the relevant code.
If you are describing behavior you have not verified in the source, say so
explicitly rather than stating it as fact.
```

Distinct from tool grounding: that one is about *file contents*, this one is about *claims*. An agent can read the right file and still assert something the code does not say.

## General solutions, not test-fitting

**Symptom:** hardcodes values to make a specific test pass; special-cases the input from the failing case.

```text
Implement a general solution that works correctly for all valid inputs, not just
the test cases. Do not hard-code values or special-case specific inputs to make
tests pass.

If the tests are wrong, or the requirements are contradictory, say so instead of
writing code that games them.
```

The second paragraph is the escape hatch. Without it the model has no legitimate move when the test really is wrong.

## Reversibility and confirmation

**Symptom:** force-pushes, deletes, posts to shared systems, runs migrations.

Enumerate here rather than generalize — this is the one place where a case list beats a heuristic, because the cost of a missed case is asymmetric:

```text
Confirm with the user before: force-pushing or rewriting published history,
deleting files or branches you did not create, running database migrations,
sending anything to an external service, or any operation that is hard to undo.

Approval for one such action does not extend to the next one.
```

**This is a prompt-level convenience, not a control.** Anything that must always hold belongs in a permissions layer or a hook. See the trust-boundary section of `SKILL.md`.

## Subagent damping

**Symptom:** spawns subagents for work a single grep would do.

```text
Do not delegate work you can do directly. A subagent is worth its cost only when
the exploration is open-ended and its intermediate steps do not need to inform
your reasoning. Searching for a known string, reading a file, or checking one
function is not that.
```

See `subagents-and-multi-agent` for the independence test.

## Context awareness

**Symptom:** wraps up early, hands back partial work as the token budget shrinks.

This one belongs to `context-and-memory` — the block itself, and the inverse block for when compaction is *not* enabled, are documented there. Include it only when the strategy it describes is actually running; telling an agent compaction exists when it doesn't causes the opposite failure.

---

## Using this file

- **Add one block, re-run the failure set, keep it only if the numbers moved.** The deletion test applies to blocks you just added, not only to old ones.
- **Watch for the contradictions between them.** Persistence versus reversibility, and scope-minimalism versus persistence, are the two pairs that fight most often. Resolve them the way `SKILL.md` describes: one rule with the boundary named, not two absolutes.
- **Re-audit on model change.** Every block here encodes a capability gap. Several of these were essential two model generations ago and are now suppressing behavior you would rather have.
