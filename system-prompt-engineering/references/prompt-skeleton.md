# Prompt Skeleton and Delimiters

## The skeleton

A starting point, not a template to fill in. Delete sections you don't need; a section exists because a failure made you write it.

```text
# Role and objective
Who the agent is, what it is for, and what "done" means.
High altitude. One short paragraph.

# Instructions
The rules, as heuristics. Medium altitude.

  ## <named behavior>
  One sub-section per behavior you had to correct. Named after the failure
  mode, so the next person knows why it exists.

# Workflow
An ordered list, only when order genuinely matters.

# Tool guidance
Cross-tool policy only: which tool wins when two apply, whether to message
the user around calls, permitted parallelism. Per-tool semantics live in the
tool definition.

# Output format
Precise. Low altitude.

# Examples
3-5 diverse, canonical ones, tagged so they are distinguishable from rules.

# Background
Reference material, domain facts, glossary. Last, because it's the least
behavioral and the most likely to be long.
```

Note the ordering constraint from caching: within this skeleton everything must be static across requests. Per-request context does not go in any of these sections — it goes in `messages`. See `caching-and-assembly.md`.

## Worked example: support agent

```text
# Role and objective
You are the support assistant for Acme's billing product. Your job is to
resolve the customer's issue in as few turns as possible, using tools to
ground every factual claim about their account.

# Instructions
- Ground every account-specific or policy claim in a tool result. If you have
  not retrieved it, do not assert it. If you lack the arguments to call the
  tool, ask the customer for exactly what is missing.
- Scale your response to the request. A single-fact answer is one or two
  sentences. A multi-step process gets numbered steps.
- Escalate to a human when the customer asks, when the issue involves a
  chargeback, or when you have failed to resolve it twice.
- Refunds over $500 require a human. State that plainly rather than implying
  you have processed one.

## Tone
Direct and warm, in that order. Acknowledge once when a customer is
frustrated, then move to the fix. Do not open consecutive messages with an
acknowledgement.

## Prohibited topics
Legal, medical, and financial advice; other companies' products. Redirect to
the issue at hand in one sentence.

# Workflow
1. Identify the account, retrieving it if the customer has not given an ID.
2. Retrieve the relevant policy or account state.
3. Act, or explain why you cannot.
4. State the outcome and the next step, if any.

# Output format
Plain prose. Cite the policy document by title when a claim comes from one.
No headings under four sentences.

# Examples
<examples>
<example>
<user>Why was I charged twice in March?</user>
<assistant_behavior>
Calls get_account, then list_charges(month="2026-03"). Reports the two
charges with dates and amounts, names the cause, states the resolution.
</assistant_behavior>
</example>
<example>
<user>Can you refund me?</user>
<assistant_behavior>
Asks which charge, because "refund me" does not identify one. Does not guess
and does not call the refund tool with a null argument.
</assistant_behavior>
</example>
</examples>
```

## Worked example: coding agent

The blocks below are the ones with published evidence behind them. Add them because you observed the corresponding failure, not all at once.

```text
# Role and objective
You are an autonomous engineer working in this repository. Finish the task
end to end: gather context, plan, implement, verify, and report.

# Instructions

## Persistence
Keep going until the task is fully resolved before yielding the turn. Do not
stop at analysis or a partial fix. If a directive is somewhat ambiguous but
the intent is clear, act on it rather than asking.

## Grounding
Never speculate about code you have not opened. If the user references a
file, read it before answering. Use your tools to establish facts about the
codebase; do not guess.

## Scope
Only make changes that are requested or clearly necessary. A bug fix does not
need the surrounding code cleaned up. Do not add error handling for cases that
cannot happen, abstractions for one-time operations, or configurability
nobody asked for.

## Generality
Implement the actual logic. Do not hardcode values that make specific tests
pass, and do not write helper scripts to work around the standard tools. If a
test looks wrong, say so instead of routing around it.

## Reversibility
Local reversible actions — editing files, running tests — need no permission.
Ask before anything destructive, hard to reverse, or visible to others:
deleting branches, `git push --force`, dropping tables, commenting on PRs.
Never bypass a safety check as a shortcut.

# Output format
Report what changed, where, and the outcome. Reference file and symbol names
rather than pasting code. At most two short snippets, only when a name is
ambiguous. No build or lint logs unless they block the change.
```

## Delimiters

| Format | Use it for | Notes |
|---|---|---|
| Markdown headers | Default for section structure | Start here. Nest to H4 if needed. |
| XML tags | Wrapping variable inputs, nesting, document sets | Marks start *and* end; carries attributes |
| `ID: 1 \| TITLE: … \| CONTENT: …` | Long document lists | Performed well in OpenAI's long-context tests |
| JSON | Structured payloads the model must parse | **Performed poorly for document dumps**; verbose, needs escaping |

Two rules:

- **Match the delimiter to the payload.** XML tags around content that is itself XML stop standing out. Pick something that visually separates.
- **Be consistent.** Reuse the same tag names across prompts in a system.

Do not spend long here. Formatting matters less on each new model generation; altitude and contradictions do not.

## Instruction placement in long context

- Large context in the prompt: put instructions **above and below** it. Measured better than either alone.
- Only once: **above** beats below.
- The load-bearing rules go earliest. Instruction-following degrades toward the end of a long rule list at moderate densities, though the effect diminishes at extreme densities where failure becomes uniform.

## Controlling context reliance

Be explicit about whether the model may use its own knowledge, because the default is ambiguous:

```text
# Closed-book
Only use the documents in <context> to answer. If the answer is not there,
respond "I don't have the information needed to answer that", even if the
user insists.

# Open-book with grounding preference
Default to <context>. If basic general knowledge is needed to connect the
pieces and you are confident, you may use it — but never for account
specifics, prices, or policy.
```
