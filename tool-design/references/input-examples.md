# Tool Use Examples

`input_examples` fixes the **right tool, wrong arguments** failure. It is an optional array of example input objects on the tool definition, and it is the cheapest fix available for conventions the schema cannot express.

Anthropic reports it taking accuracy from **72% to 90%** on complex parameter handling.

```python
{
    "name": "create_ticket",
    "description": "...",
    "input_schema": {...},
    "input_examples": [ ... ],       # 1–5 examples
}
```

Each example must validate against the tool's `input_schema` — an invalid example returns a 400, which is a useful guard against the examples drifting from the schema.

Not supported on server tools (web search, code execution) or the computer-use and browser-use toolsets. It works on user-defined tools and on Anthropic-schema client tools otherwise. Deferred tools keep their examples: when tool search discovers one, the API expands `input_examples` along with the definition.

## What schema cannot say

JSON Schema defines what is *structurally valid*. It cannot express:

| Convention | Schema can't say it | Examples can show it |
|---|---|---|
| Date format | `format: "date"` is not reliably enforced | `"2026-11-06"` |
| ID shape | `pattern` is not reliably enforced | `"USR-12345"` |
| Casing convention | Nothing expresses it | `["bug", "authentication"]` |
| Which optional fields co-occur | Conditional subschemas are outside the supported subset | Three examples with different combinations |
| Nested object assembly | Structure only, not which parts to populate when | A fully-populated `reporter` next to a minimal one |

The fourth row is the one that pays for the tokens. Co-occurrence is the hardest thing to write in prose and the easiest to show.

## The three-example pattern

Minimal, partial, full. In that order of what they teach, though the array order does not matter much.

```python
"input_examples": [
    # full — every convention on display at once
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
    # partial — a different, legitimate combination
    {
        "title": "Add dark mode support",
        "labels": ["feature-request", "ui"],
        "reporter": {"id": "USR-67890", "name": "Alex Chen"},
    },
    # minimal — the floor
    {"title": "Update API documentation"},
]
```

From these three the agent learns: dates are `YYYY-MM-DD`, ids are `USR-XXXXX`, labels are kebab-case, `reporter.contact` is a nested object — and, most importantly, **which optional fields belong together**: critical bugs carry full contact plus a tight-SLA escalation; feature requests carry a reporter but no escalation; internal tasks carry a title only.

That last inference is not expressible in the schema at all. It is the reason to spend the tokens.

## Worked example: deeply nested

Show the nesting fully populated at least once, or the agent will populate the top level and stop.

```python
{
    "name": "create_deployment",
    "input_examples": [
        {
            "service": "checkout-api",
            "version": "v2.14.3",
            "targets": [
                {"region": "us-east-1", "replicas": 6,
                 "resources": {"cpu": "2000m", "memory": "4Gi"}},
                {"region": "eu-west-1", "replicas": 3,
                 "resources": {"cpu": "1000m", "memory": "2Gi"}},
            ],
            "rollout": {"strategy": "canary", "steps": [10, 50, 100],
                        "pause_seconds": 300},
        },
        {
            "service": "docs-site",
            "version": "v1.0.9",
            "targets": [{"region": "us-east-1", "replicas": 1}],
            "rollout": {"strategy": "recreate"},
        },
    ],
}
```

Two things the second example teaches that a description would struggle to: `resources` is genuinely optional inside `targets`, and `rollout.steps` belongs to `canary` and not to `recreate`. That is a conditional relationship, expressed by demonstration.

## Worked example: optional-heavy

When most parameters are optional, the risk is the agent setting all of them because they exist.

```python
{
    "name": "search_orders",
    "input_examples": [
        {"customer_id": "CUS-4410"},                              # the common case
        {"status": "pending", "placed_after": "2026-09-01"},      # a filter combination
        {"text": "damaged in transit", "status": "open",
         "team": "logistics", "limit": 50},                        # the wide case
    ],
}
```

Leading with the narrowest example is deliberate: it communicates that one filter is normal and legitimate. Without it, agents tend to fill every field, which produces over-constrained queries returning nothing — and then a retry.

## Worked example: convention-heavy

Where the format is domain-specific and a description would be a paragraph:

```python
{
    "name": "schedule_report",
    "input_examples": [
        {"name": "weekly-revenue", "cron": "0 9 * * MON",
         "recipients": ["finance@acme.com"], "format": "xlsx"},
        {"name": "daily-errors", "cron": "0 */6 * * *",
         "recipients": ["oncall@acme.com", "eng-leads@acme.com"], "format": "csv"},
    ],
}
```

Five-field cron syntax, day-of-week as an uppercase three-letter token, recipients as a list even for one address, lowercase format strings. Four conventions, zero prose.

## Rules

**1–5 examples per tool.** Diminishing returns past three for most tools; five is the ceiling worth paying for.

**Realistic data, never placeholders.** `"string"`, `"value"`, `"example@example.com"`, and `"foo"` teach nothing and actively invite the agent to emit placeholders of its own.

**Show the range**: minimal, partial, full. A set of three near-identical examples is one example at three times the cost.

**Only where non-obvious.** Examples cost roughly 20–50 tokens for simple objects and 100–200 for complex nested ones, charged on every request. A tool with two string parameters and a clear description does not need them.

**Keep them valid.** An example that violates the schema is a 400. That is a feature — it catches drift when someone edits the schema and forgets the examples — but it means examples need to be updated with the schema, so keep them adjacent in the source.

## Examples or decomposition?

Both fix wrong arguments. They fix different *kinds* of wrong.

| The ambiguity is | Fix | Why |
|---|---|---|
| **Semantic** — polarity, scope, destructive vs read-only | Decomposition (put it in the name) | The agent must not have to *reason* about it; a wrong value here is silent and confidently wrong |
| **Conventional** — formats, id shapes, co-occurrence | `input_examples` | Reasoning is not the issue; the agent simply doesn't know your conventions |

Rough test: **would a new engineer get this wrong from the schema alone, or would they get it wrong even after reading the docs?** Conventions are the first — show them. Genuinely confusable semantics are the second — encode them in the name.

Decomposition also costs tool count, and tool count degrades selection accuracy on its own. Examples cost tokens only. Where either would work, examples are the cheaper trade.

## Measuring whether they helped

Examples are a remedy for a measured failure, not a default. Run the tool-call suite with `ArgumentCorrectnessMetric` and `evaluation_params=[ToolCallParams.INPUT_PARAMETERS]` (see `eval-loop.md`) before and after:

```text
tool           | arg correctness before | after | tokens/request delta
---------------|------------------------|-------|---------------------
create_ticket  | 0.72                   | 0.90  | +180
search_orders  | 0.94                   | 0.94  | +60      ← remove these
```

The second row is the case to look for. Examples that change nothing are pure cost on every request, forever — and they are easy to accumulate, because adding them always feels like it should help.
