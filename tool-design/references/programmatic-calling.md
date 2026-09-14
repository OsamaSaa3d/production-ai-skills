# Programmatic Tool Calling

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Fixes **context bloat from tool results** — a different problem from definition bloat, with a different fix. Here the definitions are fine; the *results* flood context, and every call costs a full inference pass.

Claude writes code in a sandbox that orchestrates your tools. Only the script's final output enters context.

**Status:** no beta header. Requires the code execution tool (`code_execution_20260120`, which adds REPL persistence and programmatic tool calling) on Opus 4.5+ / Sonnet 4.5+. Earlier integrations used `code_execution_20250825` behind the `advanced-tool-use-2025-11-20` beta; check your provider's current tool reference before pinning a version string.

## Setup

```python
response = client.messages.create(
    model=MODEL,
    max_tokens=4096,
    tools=[
        {"type": "code_execution_20260120", "name": "code_execution"},
        {
            "name": "get_expenses",
            "description": (
                "Retrieve expense line items for a user and quarter.\n"
                "Returns: list of objects with\n"
                "  - amount (float): USD\n"
                "  - category (str): one of 'travel', 'meals', 'lodging'\n"
                "  - date (str): ISO 8601\n"
                "  - merchant (str)"
            ),
            "input_schema": {...},
            "allowed_callers": ["code_execution_20260120"],
        },
    ],
    messages=[...],
)
```

`allowed_callers` is the opt-in, per tool. Without it a tool stays callable only by Claude directly.

## What Claude writes

```python
team = await get_team_members("engineering")
expenses = await asyncio.gather(*[get_expenses(m["id"], "Q3") for m in team])

exceeded = [
    {"name": m["name"], "spent": total, "limit": budgets[m["level"]]["travel_limit"]}
    for m, exp in zip(team, expenses)
    if (total := sum(e["amount"] for e in exp)) > budgets[m["level"]]["travel_limit"]
]
print(json.dumps(exceeded))
```

2,000+ line items are processed in the sandbox. Claude sees the handful of people who went over. Without this, every line item would enter context — and stay there, re-billed on every subsequent turn of the loop.

## The request/response cycle

This is where implementations go wrong, because the round-trip is not the ordinary one.

1. Claude emits a `code_execution` call containing the script.
2. The sandbox runs it. When the script calls one of your tools, execution **pauses** and the API returns a `tool_use` block for that tool — carrying a `caller` field identifying the code execution environment rather than Claude.
3. You execute it and return a `tool_result` as usual.
4. The sandbox resumes the script where it paused.
5. Steps 2–4 repeat for each tool call the script makes.
6. The script finishes; its stdout comes back as the code execution result.

```python
for block in response.content:
    if block.type == "tool_use":
        result = TOOL_REGISTRY[block.name](**block.input)
        pending.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(result)})

# When responding to a pending programmatic call, the user message must contain
# ONLY tool_result blocks — no text.
messages.append({"role": "user", "content": pending})
```

The no-text rule is easy to violate if you have a helper that always prepends a note, and it fails as a 400 rather than silently.

**Note `code_execution_20260521` returns `bash_code_execution_tool_result` with `.content.stdout`, not the legacy bare `code_execution_tool_result`.** Match on the correct block type for the tool version you declared.

## Errors inside the sandbox

Your tool's error becomes an exception in Claude's script. Two consequences:

**Return structured errors, not tracebacks.** The script may catch and handle them, so make them catchable and informative:

```python
return {"error": "no_expenses_found", "user_id": user_id,
        "hint": "User may not have submitted for this quarter."}
```

**Expect partial results.** A script using `asyncio.gather` over twenty calls where three fail may print results for seventeen. That is usually correct behavior — but your prompt should tell Claude to report which ones failed, or the omission is silent.

Unhandled exceptions surface as a failed code execution with a traceback in stderr. Claude typically rewrites the script and retries, which is fine once and expensive three times.

## Document return formats obsessively

This matters more here than anywhere else in tool design. **Claude is writing parsing code against your output.** It needs field names, types, and shapes before it has seen a single result.

```python
# BAD — Claude has to guess, then fix the script when it guesses wrong
"description": "Gets expenses for a user."

# GOOD — the script is right on the first try
"description": (
    "Retrieve expense line items for a user and quarter.\n"
    "Returns: list of objects with\n"
    "  - amount (float): USD\n"
    "  - category (str): one of 'travel', 'meals', 'lodging'\n"
    "  - date (str): ISO 8601\n"
    "Returns an empty list if the user has no expenses for that quarter."
)
```

Document the empty case and the error case too. A script that assumes a non-empty list crashes on the first user with no expenses.

## Reported impact

- Average token usage 43,588 → 27,297 (**37% reduction**) on complex research tasks.
- Internal knowledge retrieval 25.6% → 28.5%; GAIA 46.5% → 51.2%.
- On a 75-tool project-management benchmark, ~38% fewer billed input tokens with no accuracy change.
- Across production traffic with 10–49 tool definitions, typical savings of 20–40%.

**It can cost more.** On τ²-bench, where each turn makes one or two sequential tool calls, scores were unchanged and cost rose ~8%. The sandbox round-trip is overhead when there is nothing to orchestrate.

## Use when / skip when

**Use when:** three or more dependent tool calls; large datasets where you only need aggregates; filtering or transforming before Claude sees results; parallel operations across many items; intermediate data that should not influence Claude's reasoning.

**Skip when:** single-tool invocations; quick lookups with small responses; sequential workflows that make one call per turn; or when Claude genuinely *should* reason over every intermediate result.

That last one is a real case and it is easy to miss. If the task is "read these ten documents and synthesize," hiding the documents in a sandbox defeats the purpose. Programmatic calling is for data Claude needs *processed*, not data Claude needs to *read*.

## Choosing which tools to opt in

Good candidates are **independent** (parallelizable) and **idempotent** (safe to retry — a script may be rewritten and re-run after a failure).

```python
get_expenses       → yes.  read-only, independent, returns bulk data
search_tickets     → yes.  same shape
issue_refund       → no.   side-effecting, and a rewritten script re-runs it
send_email         → no.   same
delete_records     → absolutely not
```

Opt in selectively. `allowed_callers` is per tool for exactly this reason: a side-effecting tool reachable from a script that may be retried is a way to issue the same refund twice.

## Incompatibilities

Programmatic tool calling does not combine with:

- `strict: true`
- `disable_parallel_tool_use`
- forced `tool_choice`
- MCP tools

Losing `strict` is the one that costs you: arguments the script passes are not grammar-constrained. Validate them in your tool implementation. That validation is worth having regardless — it is the same check that makes error returns useful.

## Operational notes

- Tool results from programmatic calls **don't count toward input/output token usage** — that is where the savings come from.
- Container data is retained up to 30 days. Factor that into your data-handling review before putting regulated data through a sandbox.
- The sandbox is a real execution environment. Everything your tools can reach, a generated script can reach, in whatever combination it constructs. Scope the opted-in tool set accordingly.

## Verify the shape of your workflow first

Before enabling it, count: **how many tool calls does a typical task make, and are they dependent?**

```text
one call per turn, sequential        → skip. costs ~8% more, buys nothing.
3+ calls, results feed each other    → use it.
N parallel calls over a list         → use it, biggest win.
large results, small answer          → use it, second biggest win.
```

Then measure both directions — tokens *and* accuracy — before and after. This is the feature most likely to be enabled on the wrong workflow shape, because the token-savings headline sounds unconditional and is not.
