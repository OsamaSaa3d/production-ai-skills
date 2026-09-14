# The Agent-Computer Interface Checklist

If you build an agent, the tools *are* the product. Anthropic reports spending more time optimizing the tools than the overall prompt on their SWE-bench agent — the interface between model and environment deserves as much prompt-engineering attention as the system prompt, and usually gets none.

This is the checklist with before/after examples. The full treatment — decomposition, `input_examples`, tool search, programmatic calling, and the measurement loop — is the `tool-design` skill.

## 1. Descriptions are docstrings for a new engineer

The description is fed to the model on every request. Vague descriptions cause misuse, and misuse looks like a model problem.

```python
# BEFORE
{"name": "search", "description": "Search for stuff."}

# AFTER
{
    "name": "search_support_tickets",
    "description": (
        "Search the support ticket store by text, status, and date range. "
        "Returns ticket id, title, status, and opened_at — not the ticket body; "
        "use get_ticket for that. Use when the user asks about past issues or "
        "patterns across tickets. Do not use for live chat sessions, which are "
        "in a different store."
    ),
}
```

Cover: what it does, when to use it, **when not to**, what each parameter means, and what it does *not* return. Aim for three or four sentences; more if the tool is complex. The "what it does not return" clause prevents the most common wasted turn — the agent calling the tool, not finding a field, and calling it again with different arguments.

## 2. Choose formats the model writes naturally

Some output formats require the model to do bookkeeping before it can write a token. That bookkeeping is where errors come from.

| Format | Hidden cost |
|---|---|
| Unified diff | Requires counting line numbers before writing anything |
| JSON-wrapped code | Requires escaping quotes, newlines, backslashes correctly |
| Markdown / plain text | Neither |

Anthropic's finding is concrete: on a text-editor tool, formats that avoid pre-writing bookkeeping produce fewer errors. Prefer `old_string` / `new_string` replacement over line-numbered patches; prefer a raw code block over a JSON string containing code.

The general rule: **if the model has to compute something before it can start writing, it will sometimes compute it wrong.**

## 3. Leave room to think

A format the model cannot back out of, chosen before it has reasoned, is a trap.

```python
# BEFORE — the first token commits to a path
{"properties": {"action": {"enum": ["approve", "deny"]}}}

# AFTER — reasoning precedes the commitment
{"properties": {
    "reasoning": {"type": "string", "description": "Why this decision, citing the policy."},
    "action": {"enum": ["approve", "deny", "needs_human"]},
}}
```

Fields generate in order, so a reasoning field declared first is thinking; declared last, it is rationalization. Note `needs_human` as well — a binary choice with no escape hatch forces a decision on cases that deserve neither answer.

## 4. Poka-yoke the arguments

Make the mistake impossible rather than documenting it.

```python
# BEFORE — relative paths. The agent must track its own working directory
#          across turns, and it sometimes doesn't.
{"path": {"type": "string", "description": "Path to the file"}}

# AFTER — absolute paths. An entire failure class removed.
{"path": {"type": "string",
          "description": "Absolute path, e.g. /repo/src/auth.py. Relative paths rejected."}}
```

Anthropic reports that switching to absolute filepaths removed an entire class of failure in their SWE-bench agent. Look for the same shape elsewhere:

- **Enums over free strings** wherever the value set is known. `enum` is one of the few constraints genuinely enforced during generation.
- **Explicit units in the parameter name.** `timeout_seconds`, not `timeout`. `amount_usd`, not `amount`.
- **Unambiguous names.** `user_id`, not `user` — the latter invites a username.
- **Polarity in the tool name**, not in a mode flag, when getting it wrong is silent and damaging. `filter_excluding_value` cannot be inverted the way `mode="exclude"` can. Apply this only where a measurement shows the flag being set wrong; splitting preemptively inflates tool count, which degrades selection on its own.

## 5. Return high-signal context

Return what informs the next action; drop the rest.

```python
# BEFORE
{"uuid": "8f14e45f-ea", "mime_type": "application/pdf",
 "256px_image_url": "...", "created_ts": 1736899200}

# AFTER
{"name": "Q3-forecast.pdf", "file_type": "pdf", "url": "...",
 "created": "2026-01-15"}
```

**Resolve cryptic identifiers to semantic ones.** Replacing arbitrary UUIDs with meaningful names — or even a 0-indexed scheme — measurably improves retrieval precision and reduces hallucination.

When the agent sometimes needs technical IDs for a follow-up call, expose a `response_format` enum (`"concise"` / `"detailed"`) rather than always returning everything. In Anthropic's Slack tooling, `concise` responses used roughly a third the tokens of `detailed` ones.

## 6. Errors steer, they do not report

An error the agent cannot act on wastes a turn and often triggers a retry of the identical call.

```python
# BEFORE
{"error": "ValidationError: invalid input"}

# AFTER
{"error": "date_range too large (max 90 days). Retry with a narrower range, "
          "e.g. start_date='2026-01-01', end_date='2026-03-01'. For longer "
          "spans, call repeatedly and aggregate."}
```

Same for truncation: say "this result was truncated at 100 rows; narrow the filter or paginate with `offset`," not "…".

## 7. Build tools for tasks, not for endpoints

Endpoint count is not tool count. Agents have different affordances than programs — context is scarce, so a tool that returns everything and makes the agent scan it wastes the resource that matters.

```text
list_users + list_events + create_event            →  schedule_event
get_customer + list_transactions + list_notes      →  get_customer_context
read_logs (returns everything)                     →  search_logs (returns matches)
```

Each tool should have a clear, distinct purpose matching how a human would subdivide the task. Overlapping tools distract the agent from efficient strategies.

## 8. Test with real inputs and iterate

Small description changes produce large effects. Claude Sonnet 3.5's SWE-bench Verified result came substantially from precise tool-description refinements. Anthropic also found Claude appending `2025` to web search queries unprompted, degrading results — the fix was a description change, and it was only findable by reading transcripts.

The minimum loop:

1. Write realistic tasks — ones that need several tool calls and do not name the tool in the prompt. "Customer 9182 reported being charged three times; find the relevant log entries and determine if other customers were affected" is a strong task; "search the payment logs for customer_id=9182" is not.
2. Run each in a plain `while` loop against the real API.
3. Track tool calls per task, errors by type, tokens, and runtime — not just accuracy.
4. **Read the raw transcripts.** What the agent omits from its explanation matters as much as what it says.
5. Hold out a test set so you don't overfit descriptions to your examples.

Use `evals-before-shipping` for the harness, with tool-correctness and argument-correctness as the primary measures.

## The diagnostic table

| Symptom | Fix |
|---|---|
| Wrong tool chosen | Naming, namespacing, removing near-identical names |
| Right tool, wrong arguments | `input_examples`, or decomposition if the ambiguity is semantic |
| Same tool called repeatedly with no progress | Error text that steers; better return format |
| Definitions eating context | Deferred loading plus a tool search tool |
| Results eating context | Pagination, filtering, or programmatic tool calling |
| Agent ignores a tool entirely | Description doesn't say *when* to use it |

Each of these is a remedy for a measured failure, not a default. Write the natural tool first, measure, then apply the one the measurement points to.
