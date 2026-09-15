---
name: tool-design
description: Use when designing, naming, or refactoring tools for an LLM agent — writing a new tool, building an MCP server, wrapping an API as agent tools, or fixing an agent that calls the wrong tool or passes wrong arguments. Use it when tool definitions are eating the context window, when an agent has more than ~10 tools, when tool results are large, or when an agent must query a custom syntax — a search DSL, a filter grammar — and the plan is to describe it in the prompt and parse what the model emits.
version: 1.0
---

# Tool Design for Agents

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

A tool is a contract between a deterministic system and a non-deterministic agent. Design it for the agent, not for a developer. The tools that work best are the ones where the right call is obvious from the name and schema alone.

Three failure modes, each with a different fix. Diagnose before you reach for a feature:

| Symptom | Fix |
|---|---|
| Agent picks the wrong tool | Naming and namespacing |
| Agent picks the right tool, wrong arguments | `input_examples`, or decomposition |
| Tool definitions eat the context window | `defer_loading` + tool search |
| Intermediate results eat the context window | `allowed_callers` + programmatic calling |

The field names in that table (`input_examples`, `defer_loading`, `allowed_callers`) are the Anthropic API's spelling. Other providers expose some of these under different names and some not at all — the *diagnosis* column is portable, the spelling is not. Check your provider's current tool reference for the equivalent before reaching for one.

**These are remedies, not defaults.** Every one of them costs something — tool count, tokens, latency, or complexity. Write the natural tool first, measure it against a tool-call eval suite, and apply a fix only where the measurement shows a failure. See the measurement loop below; it is the part of this skill that makes the rest safe to use.

## Avoid / Prefer

The table above diagnoses failures. This one is about the shape of the interface you write before any of them show up.

| Avoid | Prefer |
|---|---|
| Query-string or DSL parameter | Typed fields with enums, query built in code |
| One tool per API endpoint | One tool per task the agent actually performs |
| Everything returned by default | High-signal fields, with a `response_format` enum for the rest |
| Raw UUIDs in tool output | Names or indices the agent can reason about |
| Unbounded tool responses | Pagination, filtering, and a deliberate token cap |
| Tracebacks as error text | Errors that name the next action to take |
| Names differing by one token | Namespaced names distinguishable at a glance |

These are defaults for the common case; the sections below name the conditions under which each one flips.

## Minimal pattern

```text
Agent needs to reach a system?
    |
    v
Name the tool for the task, not for the endpoint
    |
    v
Take typed fields; construct the query in your code
    |
    v
Return high-signal fields, capped and paginated
    |
    v
Run a task set that asserts tool AND arguments
    |
    v
Add a remedy only where that measurement showed a failure
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## Wrong arguments on a mode flag: move the discriminator into the name

**Do not apply this by default.** Write the single tool with its mode parameter, run it against your eval suite, and decompose only if the agent demonstrably gets the flag wrong. Decomposition buys per-call clarity at the cost of tool count, and tool count degrades selection accuracy on its own — so applying it preemptively can trade one failure mode for a worse one.

When it *is* warranted: a tool whose behavior branches on a polarity or mode parameter requires the agent to get both the tool selection and the flag right. Inverting flags are the worst case, because a wrong value is structurally valid, raises no error, and returns confidently wrong results. Nothing in the transcript looks broken. That silence is what makes this failure worth spending tool count to eliminate — unlike a malformed argument, it will not surface on its own.

If the eval shows it, decompose into separately named tools.

```python
# BAD — polarity lives in a parameter
{
    "name": "filter_records",
    "input_schema": {
        "properties": {
            "field": {"type": "string"},
            "value": {"type": "string"},
            "mode": {"type": "string", "enum": ["include", "exclude"]},
        },
        "required": ["field", "value", "mode"],
    },
}

# GOOD — polarity lives in the name
{
    "name": "filter_records_including_value",
    "description": "Return only records where <field> equals <value>.",
    "input_schema": {
        "properties": {"field": {...}, "value": {...}},
        "required": ["field", "value"],
    },
},
{
    "name": "filter_records_excluding_value",
    "description": "Return all records except those where <field> equals <value>.",
    "input_schema": {
        "properties": {"field": {...}, "value": {...}},
        "required": ["field", "value"],
    },
}
```

**Worked example of the loop.** A tool taking a `= x` / `≠ x` mode parameter was measured against a task set covering both polarities. The agent selected the tool correctly but set the mode wrong intermittently — the failure only visible because the suite asserted expected arguments, not just expected tool names. Splitting into two tools with `include` and `exclude` in the names, parameters otherwise identical, took the re-run to correct calls every time.

Note the order: the single tool came first, the measurement identified the specific failure, and decomposition was the response. Running the same loop on your own tools may show the flag is handled fine, in which case the second tool is pure cost.

Why it works when it works: Anthropic's tool-writing guidance holds that tools whose names reflect natural subdivisions of tasks offload agentic computation out of the agent's reasoning and back into the tool boundary, reducing overall risk of mistakes. The agent does not have to *reason* about polarity if the name already encodes it.

**Where the tradeoff flips.** Reserve decomposition for semantics the agent must not invert — polarity, destructive vs read-only, scope. Do not split on every enum value: a `status` parameter with six values should stay one parameter, not become six tools. If you find yourself decomposing past two or three variants, `input_examples` is the cheaper fix.

Related naming rules:

- **Namespace by service and resource** — `asana_search`, `jira_search`; `asana_projects_search`, `asana_users_search`. Prefix vs suffix namespacing has measurable and model-dependent effects, so pick based on your own eval.
- **Avoid near-identical names.** `notification-send-user` vs `notification-send-channel` is a documented source of wrong-tool selection. If two names differ by one token, the agent will sometimes take the wrong one.
- **Name parameters unambiguously.** `user_id`, not `user`.

## Build tools for tasks, not for API endpoints

Do not mechanically wrap each API endpoint as a tool. Agents have different affordances than programs: context is scarce, so a tool that returns everything and makes the agent scan it wastes the resource that matters.

Consolidate frequently-chained operations into one tool:

```
list_users + list_events + create_event   →   schedule_event
read_logs                                  →   search_logs
get_customer_by_id + list_transactions + list_notes  →  get_customer_context
```

Each tool should have a clear, distinct purpose that matches how a human would subdivide the task. Overlapping tools distract the agent from efficient strategies.

## Take fields, not strings: never make the agent write a query language

The instinct when an agent needs to query something with a custom syntax — a search DSL, a filter grammar, a reporting language — is to describe the language in the system prompt and let the model emit queries as text. It reads like the flexible option. It is the brittle one.

```python
# BAD — the model emits a string in a grammar you then have to parse
SYSTEM = """Query syntax: field:value, field:>value, field:[a TO b],
AND / OR / NOT ...400 more tokens of grammar... Emit only the query string."""

query = model_output.strip()        # sometimes fenced, sometimes prose-wrapped,
rows = db.execute(compile(query))   # sometimes subtly invalid grammar
```

```python
# GOOD — typed fields in, query constructed in code
{
  "name": "search_tickets",
  "description": "Search the ticket store. Returns id, title, status, opened_at.",
  "input_schema": {
    "type": "object",
    "properties": {
      "text":     {"type": "string", "description": "Free-text match on title and body"},
      "status":   {"type": "string", "enum": ["open", "closed", "pending"]},
      "team":     {"type": "string", "enum": ["platform", "billing", "growth"]},
      "opened_after": {"type": "string", "format": "date"}
    },
    "additionalProperties": false
  }
}
```

The agent's job shrinks to understanding intent and picking fields. Your code owns the grammar. Four reasons, strongest first:

**Safe by construction.** A model emitting executable query text from user-controlled input is an injection surface. With typed fields, a successful injection yields a wrong-but-well-formed query over fields you allowlisted — never arbitrary query text.

**Enforcement instead of parsing.** A DSL string in prose is the one output mode with no constraint available; a tool schema is validated at generation time. "Parsing is unreliable" understates it — you opted out of the guarantee rather than losing it.

**Invalid states stop being representable.** An enum of three statuses cannot produce a fourth. A prose grammar produces anything the model finds plausible, and the dangerous failures are the subtle ones: valid syntax, wrong semantics, passes your parser, returns wrong rows.

**The definition can be deferred; a prompt grammar cannot.** Both cost tokens, so this is not automatic — but a tool definition can sit behind `defer_loading` and enter context only when relevant, while prompt grammar is resident on every request and competes for attention with every other instruction there.

**The limit: this works when the field space is enumerable.** If users need open analytical queries over a schema they explore freely, the answer is not a prompt-described grammar either — it is generated SQL behind a validation gate: parsed, checked against an allowlisted schema, run read-only with a row cap. A deliberate exception with its own safeguards, not the default.

## Return high-signal context

Return what informs the agent's next action. Drop what doesn't.

- Prefer `name`, `file_type`, `image_url` over `uuid`, `mime_type`, `256px_image_url`.
- **Resolve cryptic identifiers to semantic ones.** Replacing arbitrary alphanumeric UUIDs with meaningful names — or even a 0-indexed scheme — measurably improves retrieval precision and reduces hallucination.
- When the agent sometimes needs technical IDs for downstream calls, expose a `response_format` enum rather than always returning everything:

```python
{
    "name": "search_threads",
    "input_schema": {
        "properties": {
            "query": {"type": "string"},
            "response_format": {
                "type": "string",
                "enum": ["concise", "detailed"],
                "description": "Use 'concise' unless you need IDs for a follow-up call.",
            },
        },
    },
}
```

In Anthropic's Slack tooling, `concise` responses used roughly one third the tokens of `detailed` ones.

Response structure (JSON vs XML vs Markdown) also measurably affects performance, with no universal winner. Test it.

## Budget tool response size

Implement pagination, range selection, filtering, and truncation with sensible defaults. For a reference point, Claude Code caps tool responses at 25,000 tokens by default; pick your own cap deliberately rather than inheriting whatever your harness does.

When you truncate or error, **steer the agent in the response text**. An error should say what to do differently, not emit a traceback:

```python
# BAD
return {"error": "ValidationError: invalid input"}

# GOOD
return {
    "error": (
        "date_range too large (max 90 days). "
        "Retry with a narrower range, e.g. start_date='2026-01-01', end_date='2026-03-01'. "
        "For longer spans, call repeatedly and aggregate."
    )
}
```

Same for truncation: tell the agent to make several narrow searches rather than one broad one.

## Tool use examples: fix wrong arguments

*`input_examples` is an Anthropic API field. Where a provider has no equivalent, the same information goes in the parameter descriptions — more verbosely, and charged the same way.*

When the agent picks the right tool but malformed arguments, JSON Schema has run out of expressive power. Schema defines what is *structurally valid*; it cannot express conventions — date format, ID shape, which optional parameters co-occur.

Add `input_examples` to the tool definition:

```python
{
    "name": "create_ticket",
    "input_schema": {...},
    "input_examples": [
        # full specification
        {
            "title": "Login page returns 500 error",
            "priority": "critical",
            "labels": ["bug", "authentication", "production"],
            "reporter": {
                "id": "USR-12345",
                "name": "Jane Smith",
                "contact": {"email": "jane@acme.com", "phone": "+1-555-0123"},
            },
            "due_date": "2026-11-06",
            "escalation": {"level": 2, "notify_manager": True, "sla_hours": 4},
        },
        # partial
        {
            "title": "Add dark mode support",
            "labels": ["feature-request", "ui"],
            "reporter": {"id": "USR-67890", "name": "Alex Chen"},
        },
        # minimal
        {"title": "Update API documentation"},
    ],
}
```

From three examples the agent learns date format (`YYYY-MM-DD`), ID convention (`USR-XXXXX`), label casing (kebab-case), how to build the nested `reporter` object, and — most importantly — *which optional fields go together*: critical bugs carry full contact plus tight-SLA escalation, feature requests carry a reporter but no escalation, internal tasks carry a title only.

Anthropic reports this took accuracy from 72% to 90% on complex parameter handling.

**Rules:** 1-5 examples per tool. Realistic data, never `"string"` or `"value"`. Show minimal, partial, and full patterns. Only add examples where correct usage is genuinely non-obvious from the schema — they cost tokens.

This is an alternative to name-decomposition for the wrong-argument problem. Decomposition is better when the ambiguity is semantic (polarity, scope); examples are better when it's conventional (formats, co-occurrence).

## Tool search: fix context bloat from definitions

*`defer_loading` plus a server-side search tool is an Anthropic API feature. The portable version of this idea is filtering the tool array per request in your own code — cheaper to build, and it works anywhere; see `llm-tool-calling/references/many-tools.md`.*

Tool definitions are charged on every request before any work happens. Five MCP servers can run 55K tokens; Anthropic measured 134K before optimizing.

Mark tools `defer_loading: true` and add a search tool. Only the search tool (~500 tokens) plus your always-loaded tools enter context upfront; the rest are discovered on demand.

```python
client.messages.create(
    model="...",
    max_tokens=4096,
    tools=[
        # regex variant; BM25 variant is tool_search_tool_bm25_20251119
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},

        {"name": "github_create_pull_request", "description": "...",
         "input_schema": {...}, "defer_loading": True},
        # ... hundreds more deferred
    ],
)
```

For whole MCP servers:

```python
{
    "type": "mcp_toolset",
    "mcp_server_name": "google-drive",
    "default_config": {"defer_loading": True},
    "configs": {"search_files": {"defer_loading": False}},  # keep the hot one loaded
}
```

**Reported impact:** ~72K tokens of definitions down to ~8.7K total context consumption, an 85% reduction. Accuracy on internal MCP evals went from 49% to 74% (Opus 4) and 79.5% to 88.1% (Opus 4.5).

**Use when:** definitions exceed ~10K tokens, you have 10+ tools, you're running multiple MCP servers, or you have tool-selection accuracy problems.
**Skip when:** fewer than 10 tools, all tools used every session, or definitions are already compact.

Two things that make it work:

1. **Search matches names and descriptions**, so vague names break discovery. `search_customer_orders` with a description naming the filters and return fields is discoverable; `query_db_orders` / "Execute order query" is not.
2. **Keep your 3-5 most-used tools loaded** (`defer_loading: False`) and defer the rest. Add a system prompt line naming the available categories so the agent knows what to search for.

Deferred tools don't break prompt caching — they're excluded from the initial prompt entirely, so the cacheable prefix stays stable.

## Programmatic tool calling: fix context bloat from results

*`allowed_callers` plus a code-execution tool is an Anthropic API feature. Providers offering a code interpreter with callable user tools support the same pattern under other names; without one, the portable substitute is doing the aggregation in your own tool implementation and returning only the result.*

Different problem, different fix. Here the definitions are fine but *results* flood context, and each call costs a full inference pass.

Mark tools callable from code, enable code execution, and the agent writes Python that orchestrates them in a sandbox. Only the script's final output enters context.

```python
client.messages.create(
    model="...",
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
                "  - date (str): ISO 8601"
            ),
            "input_schema": {...},
            "allowed_callers": ["code_execution_20260120"],
        },
    ],
)
```

The agent then writes something like:

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

2,000+ expense line items are processed in the sandbox; the agent sees only the handful of people who went over.

**Document return formats in the description.** The agent is writing parsing code against your output — it needs field names and types, as in the `get_expenses` description above. This matters more here than in ordinary tool use.

**Reported impact:** average token usage 43,588 → 27,297 (37% reduction) on complex research tasks. Internal knowledge retrieval 25.6% → 28.5%; GAIA 46.5% → 51.2%. On a 75-tool project-management benchmark, ~38% fewer billed input tokens with no accuracy change. Across production traffic with 10-49 tool definitions, typical savings of 20-40%.

**It can cost more.** On τ²-bench, where each turn makes one or two sequential tool calls, scores were unchanged and cost rose ~8%. Sequential single-call workflows do not benefit.

**Use when:** 3+ dependent tool calls, large datasets where you only need aggregates, filtering or transforming before the agent sees results, parallel operations across many items, or intermediate data that shouldn't influence the agent's reasoning.
**Skip when:** single-tool invocations, quick small-response lookups, or when the agent genuinely *should* reason over every intermediate result.

**Opt in selectively.** Good candidates are independent (parallelizable) and idempotent (safe to retry). Note that tool results from programmatic calls don't count toward input/output token usage, and container data is retained up to 30 days.

## Measure it — don't guess

Every rule above is a default, not a law. The effects are model-dependent and task-dependent. Anthropic's own guidance on prefix vs suffix namespacing is explicitly "run your own eval."

The loop:

1. **Prototype** the tools and wire them into a local MCP server or pass them directly to the API.
2. **Generate realistic tasks.** Strong tasks need multiple tool calls and realistic data. "Customer 9182 reported being charged three times; find the relevant log entries and determine if other customers were affected" is a strong task. "Search the payment logs for `customer_id=9182`" is a weak one — it names the tool call in the prompt.
3. **Run each task in a simple `while` loop** — LLM call, tool call, repeat — one loop per task. Direct API calls, no framework.
4. **Ask the eval agent for reasoning and feedback blocks before its tool calls.** Turn on interleaved thinking if available. This tells you *why* it picked a tool.
5. **Track more than accuracy**: tool calls per task, errors by type, tokens, runtime. Many invalid-parameter errors means descriptions need work. Many redundant calls means pagination or filtering defaults need rightsizing.
6. **Read the raw transcripts.** What the agent omits from its feedback matters as much as what it says.
7. **Hold out a test set** so you don't overfit tool descriptions to your training tasks.

Use the `evals-before-shipping` skill for the harness, with `ToolCorrectnessMetric` and `ArgumentCorrectnessMetric` as the primary measures. A/B two tool designs by running the same task set against each.

Small description changes produce large effects — Claude Sonnet 3.5's SWE-bench Verified result came substantially from precise tool description refinements. Anthropic also found Claude appending `2025` to web search queries unprompted, degrading results; the fix was a description change. You will not find these without reading transcripts.

## Pitfalls

**Wrapping your API 1:1.** Endpoint count is not tool count. Consolidate around tasks.

**Decomposing before measuring.** The include/exclude split is a fix for a failure you have observed, not a style rule. Applied preemptively across a tool library it inflates tool count — which degrades selection accuracy — to solve a problem that may not exist on your model and task.

**Splitting tools for every enum value.** Decomposition has a cost. Split on semantics the agent must not invert; keep ordinary value parameters as parameters.

**Vague names plus deferred loading.** If tools are discoverable only by search, a bad name makes a tool invisible. Fix names before enabling `defer_loading`.

**Returning raw IDs.** UUIDs in tool output cost precision. Resolve them to names or indices.

**Opaque errors.** An error the agent can't act on wastes a turn. Say what to change.

**Enabling programmatic calling on sequential workflows.** It costs more and buys nothing. Check the shape of your workflow first.

**Adding all three features at once.** Start with your actual bottleneck — wrong tool → naming, wrong arguments → examples, definition bloat → tool search, result bloat → programmatic calling. Layer only after measuring.

**Assuming a feature is available on your provider and model.** Tool search, programmatic tool calling, and `input_examples` are Anthropic API features, generally available with no beta header, but each supports an explicit list of models rather than "version X and later" — and recent models have been absent from those lists. Version strings are date-stamped and move (`code_execution_20260120` superseded `code_execution_20250825`). Search the provider's current tool reference before pinning one, and treat the absence of an equivalent elsewhere as the normal case rather than a surprise.

## Success criteria

Good tool design shows up as numbers on a held-out task set, not as a tidier schema file. Run the same tasks against the old and new designs and compare:

- **Tool-selection correctness** — `ToolCorrectnessMetric` at `threshold=1.0`. This is what naming and namespacing buy, and what inflating tool count costs. Harness: `evals-before-shipping/references/tool-call-suite.md`.
- **Argument correctness** — the same metric with `INPUT_PARAMETERS`, or `ArgumentCorrectnessMetric` where values can't be predetermined. A name-only assertion reports success on an inverted polarity flag, which is the failure this skill spends tool count to eliminate.
- **Tool calls per task.** Redundant or repeated calls mean pagination, filtering, or truncation defaults are wrong, not that the agent is confused.
- **Tokens, split two ways** — definition tokens resident on every request, and tool-result tokens per task. Tool search moves the first; programmatic calling and response budgeting move the second. Tracking one total hides which fix is working.
- **Invalid-parameter error rate, bucketed by type.** A pile of format errors points at `input_examples` or descriptions; a pile of wrong-field errors points at naming.
- **End-to-end task completion on the held-out set**, so a fix for one symptom is not quietly traded for a worse one — more tools sharpen each call and degrade selection at the same time.

If none of these move, the redesign did not help on that task set. Keep the simpler tool.

## References

- `references/naming-experiments.md` — the include/exclude experiment in full, plus a template for A/B-ing tool designs
- `references/tool-search.md` — regex vs BM25 vs custom embedding search, MCP toolset config, what stays loaded
- `references/programmatic-calling.md` — full request/response cycle including the `caller` field, error handling in sandboxed code
- `references/input-examples.md` — worked examples across nested, optional-heavy, and convention-heavy schemas
- `references/eval-loop.md` — the tool-optimization harness end to end, including held-out test sets