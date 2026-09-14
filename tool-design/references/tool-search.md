# Tool Search

Fixes **context bloat from tool definitions**. A typical multi-server setup (GitHub, Slack, Sentry, Grafana, Splunk) can consume ~55K tokens in definitions before Claude does any work. Tool search typically reduces this by over 85%, loading only the 3–5 tools needed for a given request.

It also fixes selection accuracy, which is the less-advertised half: selection degrades once you exceed roughly 30–50 available tools, and a focused on-demand set keeps it high across thousands. Reported internal MCP-eval accuracy: 49% → 74% (Opus 4), 79.5% → 88.1% (Opus 4.5).

**Status:** generally available, no beta header. Supported on Opus 4.5 and later, Sonnet 4.5 and later, Haiku 4.5, and the Fable/Mythos tiers. **Opus 4.1 and earlier do not support it.** On Amazon Bedrock it is available through InvokeModel only, not Converse.

## The two variants

```json
{"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"}
{"type": "tool_search_tool_bm25_20251119",  "name": "tool_search_tool_bm25"}
```

| | Regex | BM25 |
|---|---|---|
| Claude writes | Python `re.search()` patterns, case-insensitive | Natural-language queries |
| Max length | 200 characters | 500 characters |
| Good when | Names follow a strict convention (`github_*`, `slack_*`) | Names and descriptions are prose-like and vocabulary varies |
| Failure mode | A pattern that matches nothing — silent empty result | Lexical mismatch between the query and your wording |

Both variants search **tool names, descriptions, argument names, and argument descriptions.** That is wider than most people assume, and it means a well-named parameter contributes to discoverability.

Start with regex if your naming is disciplined, BM25 if it is not. Then A/B them on your own eval set — the difference is model- and catalog-dependent.

## Setup

```python
response = client.messages.create(
    model="claude-opus-5",
    max_tokens=2048,
    tools=[
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},

        # hot path — stays loaded, no search round-trip
        {"name": "search_customer_orders", "description": "...", "input_schema": {...}},

        # everything else
        {"name": "github_create_pull_request", "description": "...",
         "input_schema": {...}, "defer_loading": True},
        # ... up to 10,000 deferred tools
    ],
    messages=[...],
)
```

**`defer_loading` controls what enters the context window, not what you send.** You still send every tool's full definition on every request — the API needs them server-side to run the search and expand references. The saving is in context and in the system-prompt prefix, not in request size.

## What comes back

```json
{"type": "server_tool_use", "id": "srvtoolu_01ABC", "name": "tool_search_tool_regex",
 "input": {"pattern": "weather", "limit": 10}}

{"type": "tool_search_tool_result", "tool_use_id": "srvtoolu_01ABC",
 "content": {"type": "tool_search_tool_search_result",
             "tool_references": [{"type": "tool_reference", "tool_name": "get_weather"}]}}

{"type": "tool_use", "id": "toolu_01XYZ", "name": "get_weather", "input": {...}}
```

Three rules for handling it:

- **Never return a `tool_result` for the `srvtoolu_...` id.** The search ran on Anthropic's servers. Sending a result for it is rejected.
- **Pass the `server_tool_use` and `tool_search_tool_result` blocks back unchanged** in the next request's history. The API expands references throughout the history, so discovered tools stay usable in later turns without re-searching.
- **Send the same full `tools` array every time** — the search tool plus every deferred definition.

A search that matches nothing returns an empty `tool_references` array, not an error. Claude will usually search again with a broader pattern.

## MCP servers

Don't set `defer_loading` per tool for MCP-sourced tools. Set it on the toolset:

```python
{
    "type": "mcp_toolset",
    "mcp_server_name": "google-drive",
    "default_config": {"defer_loading": True},
    "configs": {"search_files": {"defer_loading": False}},   # keep the hot one loaded
}
```

This is where tool search pays best: aggregating several MCP servers is the standard way to end up with 200+ tools and no control over their naming.

## Custom search

You can implement your own discovery — embeddings, semantic search, a hand-written router — by returning `tool_reference` blocks from an ordinary tool:

```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_your_tool_id",
    "content": [{"type": "tool_reference", "tool_name": "discovered_tool_name"}],
}
```

Every referenced tool still needs a full definition in the top-level `tools` array, normally with `defer_loading: True`. Note the format difference: custom implementations use the standard `tool_result` shape with `tool_reference` content, not the server-side `tool_search_tool_result` shape.

Worth it when your tools cluster semantically in ways lexical matching misses — "refund," "chargeback," and "reversal" are the same concept to a user and three different strings to regex.

## Limits

| | |
|---|---|
| Deferred tools per request | 10,000 |
| Results per search | 5 by default; Claude may set `limit` from 1 to 10,000 |
| Regex pattern length | 200 characters |
| BM25 query length | 500 characters |

## Caching and strict mode

Both compose cleanly, which is the part people expect to break:

**Caching.** Deferred tools are excluded from the system-prompt prefix entirely. Discovered tools are appended inline in the conversation as `tool_reference` blocks and expanded there. The prefix is untouched, so the cache survives.

One constraint: **a tool with `defer_loading: true` cannot also carry `cache_control`** — the API returns a 400. Put the breakpoint on a non-deferred tool.

**Strict mode.** The grammar builds from the full toolset, so `defer_loading` and `strict: true` compose without grammar recompilation on discovery.

**`input_examples` survive too.** When a deferred tool is discovered, its examples expand along with its definition.

## Error handling

400s, which stop the request:

| Message | Cause |
|---|---|
| `At least one tool must have defer_loading=false` | You deferred everything, including the search tool |
| `Tool reference 'x' not found in available tools` | A reference points at a tool missing from `tools` |

200s, where the error is in the body as `tool_search_tool_result_error`:

| `error_code` | Meaning |
|---|---|
| `invalid_tool_input` | Malformed regex, or a pattern over 200 characters |
| `unavailable` | Search timed out or the service was unavailable |
| `too_many_requests` | Rate limited |
| `execution_time_exceeded` | Search exceeded its time limit |

The 200-status errors do not raise. Branch on the content type before reading results.

## When Claude can't find your tool

Almost always a naming problem, not a search problem.

```text
BAD:   query_db_orders        "Execute order query"
GOOD:  search_customer_orders "Search customer orders by status, date range, and
                               total. Returns order id, status, placed_at, total_usd."
```

Debugging steps:

1. Search covers names, descriptions, argument names, and argument descriptions. Check all four.
2. Test the pattern yourself: `re.search(r"your_pattern", "tool_name", re.IGNORECASE)`.
3. Matching is case-insensitive, so casing is never the cause.
4. Claude writes broad patterns (`.*weather.*`), not exact matches.
5. Add the keywords users actually say to the description.

**Fix names before enabling `defer_loading`.** A tool discoverable only by search, with a name nobody would search for, is invisible — and it fails silently, as "Claude didn't use that capability" rather than as an error.

## When to use it, and when not

**Use when:** 10 or more tools, definitions over ~10K tokens, selection accuracy dropping as the catalog grows, aggregating MCP servers (200+ tools), or a library that grows over time.

**Skip when:** fewer than 10 tools, every tool used in every request, or definitions already tiny (under ~100 tokens total). The search round-trip is not free, and on a small catalog you are paying latency for nothing.

## Make it measurable

```text
config                    | tokens upfront | first-call latency | wrong-tool rate | pass rate
--------------------------|----------------|--------------------|-----------------|----------
all loaded                |  55,000        | low                |                 |
3 hot + rest deferred     |   8,700        | +1 search hop      |                 |
all deferred but search   |   ~500         | +1 search hop      |                 |
```

Track **wrong-tool rate separately from pass rate**. Deferring can improve selection (smaller live catalog) while adding a discovery failure mode (tool never found). Those move in opposite directions and a single accuracy number hides both.
