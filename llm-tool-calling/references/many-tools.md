# Systems With Many Tools

Two separate problems get conflated here, and they have different fixes:

- **Selection accuracy** degrades as the catalog grows. The model picks the wrong tool, or invents one.
- **Context cost** grows linearly with definitions, charged on every request before any work happens.

Five MCP servers can run 55K tokens of definitions. You can have the second problem without the first — a compact catalog of 8 tools with long descriptions — and the first without the second.

## Where the cliff is

Roughly 10–20 tools in a single reasoning context is the practical safe zone, and OpenAI's own guidance suggests aiming for fewer than 20 available at the start of a turn. Above that, degradation is not graceful. Berkeley Function Calling Leaderboard data has shown accuracy on scheduling tasks collapsing from around 43% to 2% as a catalog grew from 4 tools to 51.

API-level caps are far above where real degradation starts, so "the API accepts 128 tools" tells you nothing about whether your agent will use 60 of them correctly. Measure your own number: run the tool-call eval suite from `evals-before-shipping` with 10, 20, and 40 tools loaded and watch where `ToolCorrectnessMetric` falls off. It moves with the model — small models hit the cliff earlier — which is exactly why it is worth knowing for the model you actually ship.

The failure mode is worth recognizing in transcripts: the model calls a plausible-sounding tool that does not exist, or calls the right tool with an argument borrowed from a *different* tool's schema. Both mean the catalog is crowded, not that the descriptions are bad.

## Fix 1: fix the names first

Before any mechanism, spend an hour on names. Most crowded catalogs are crowded with near-duplicates.

- **Namespace by service and resource.** `asana_projects_search`, `jira_issues_search` — not `search` and `search_2`.
- **Kill near-identical pairs.** `notification-send-user` vs `notification-send-channel` is a documented source of wrong-tool selection. If two names differ by one token, the model will sometimes take the wrong one.
- **Consolidate chains.** `list_users` + `list_events` + `create_event`, always called in that order, is one `schedule_event` tool. Endpoint count is not tool count.

This is free, it helps every other fix, and it is a prerequisite for search-based discovery — a tool nobody can name is a tool search cannot find. Full treatment in `tool-design`.

## Fix 2: filter per request

The cheapest mechanical fix. You usually know something about the request before you send it.

```python
TOOLSETS = {
    "billing":  ["get_invoice", "issue_refund", "get_payment_method"],
    "support":  ["get_ticket", "update_ticket", "escalate"],
    "readonly": ["get_invoice", "get_ticket", "search_docs"],
}

def tools_for(request):
    names = TOOLSETS[classify(request)] if request.is_classified else TOOLSETS["readonly"]
    return [t for t in ALL_TOOLS if t["function"]["name"] in names]
```

Classify with code where you can; with a small model where you can't. A cheap classifier in front of an expensive generator usually pays for itself — see `model-selection`.

The caching caveat: changing the tool array changes the cached prefix. If you have three stable toolsets, you get three cache namespaces and that is fine. If you rebuild the array per request from a relevance score, you have no cache at all. On OpenAI-compatible endpoints, `tool_choice: {"type": "allowed_tools", "mode": "auto", "tools": [...]}` narrows the permitted set without touching the definitions, which keeps the prefix stable.

## Fix 3: defer loading and let the model search

Mark tools `defer_loading: true` and add a search tool. Only the search tool (~500 tokens) plus your always-loaded tools enter context upfront; the rest are discovered on demand.

```python
tools = [
    {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
    # or: tool_search_tool_bm25_20251119 / tool_search_tool_bm25

    {"name": "search_customer_orders", "description": "...", "input_schema": {...}},   # hot, stays loaded
    {"name": "github_create_pull_request", "description": "...",
     "input_schema": {...}, "defer_loading": True},
    # ... hundreds more deferred
]
```

Reported impact: ~72K tokens of definitions down to ~8.7K total context, an 85% reduction, with internal MCP-eval accuracy rising 49% → 74% (Opus 4) and 79.5% → 88.1% (Opus 4.5). Note that both numbers moved — deferring is not only a cost fix; a smaller live catalog also selects better.

Constraints:

- **Never defer everything.** The search tool itself must not be deferred, and at least one tool must be non-deferred, or the request returns 400 `All tools have defer_loading set`.
- **Keep your 3–5 most-used tools loaded.** The hot path should not pay a search round-trip.
- **Add a system-prompt line naming the categories available**, so the model knows what to search for rather than guessing search terms.
- Deferred tools don't break prompt caching — they're excluded from the initial prompt entirely, so the cacheable prefix stays stable.

Details and the MCP toolset config in `tool-design`'s `references/tool-search.md`.

## Fix 4: dispatchers

A hand-rolled alternative when you can't use deferred loading: one tool with an action parameter, dispatched in your code.

```python
{
    "name": "github",
    "description": "GitHub operations. Call with the action you need.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string",
                       "enum": ["create_pr", "list_prs", "comment", "merge"]},
            "params": {"type": "object"},
        },
        "required": ["action", "params"],
        "additionalProperties": False,
    },
}
```

The honest tradeoff: you collapse 20 names into 1, and you give up strict typing on `params` — it is now an open object, which is exactly the constraint you were relying on. Use dispatchers when the actions share a parameter shape, and prefer deferred loading when they don't. Never use a dispatcher for a destructive action (`merge`, `delete`) whose safety depends on the schema.

## Fix 5: split across agents — last, not first

Splitting a crowded catalog across specialized subagents works, and it is the most expensive option: you pay a full extra instance, a delegation round-trip, and a new class of coordination failure. `subagents-and-multi-agent` is explicit that tool count alone is largely no longer a reason to split, precisely because deferred loading solves it.

Split when the sub-task also needs context isolation, restricted permissions, or parallelism. Splitting *only* to reduce tool count is buying coordination failures to solve something a flag fixes.

## Strict mode under a large catalog

Anthropic enforces per-request complexity limits — how many strict tools, total optional parameters, and union-typed parameters. Unions are the expensive ones; they multiply out during grammar compilation. Exceeding a limit returns a 400.

When you hit it, in order:

1. **Make optional parameters required** where a sensible default exists. Optional is what you are being charged for.
2. **Replace `anyOf` unions with an enum plus a flat field** where the union was modeling a mode rather than a genuine type choice.
3. **Flatten nested objects.** Depth costs.
4. **Reserve `strict: true` for the tools where a schema violation does damage.** A read-only search tool getting a malformed filter is a retry; a refund tool getting a malformed amount is an incident. Turn strict off on the former, keep it on the latter.

Do them in that order — the first two are free, the last one gives up a guarantee.

## The measurement

Whatever you apply, it is a hypothesis until measured:

```text
baseline        : N tools, no mechanism   → pass rate, tokens/task, wrong-tool rate
+ better names  :                         → same three
+ filtering     :                         → same three
+ defer_loading :                         → same three, plus first-call latency
```

Track the wrong-tool rate separately from overall pass rate. A change can lift the pass rate while making selection worse, if the tools it added happen to be easy ones.
