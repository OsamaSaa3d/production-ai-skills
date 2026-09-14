# The Include/Exclude Experiment, and How to A/B a Tool Design

Every rule in the tool-design skill is a default, not a law. The effects are model-dependent and task-dependent — Anthropic's own guidance on prefix vs suffix namespacing is explicitly "run your own eval." This file is the experiment that produced the decomposition rule, written out so you can run the same shape on your own tools.

## The experiment

**Hypothesis:** a tool whose behavior branches on a polarity parameter will have its polarity set wrong intermittently, and moving the polarity into the tool name will fix it.

**Setup.** One tool with a mode parameter:

```python
{
    "name": "filter_records",
    "description": "Filter records by a field value, including or excluding matches.",
    "input_schema": {
        "type": "object",
        "properties": {
            "field": {"type": "string"},
            "value": {"type": "string"},
            "mode": {"type": "string", "enum": ["include", "exclude"]},
        },
        "required": ["field", "value", "mode"],
        "additionalProperties": False,
    },
}
```

**Task set.** Tasks covering both polarities in roughly equal numbers, phrased the way a user would phrase them — never naming the tool or the parameter:

```text
"Show me only the orders from the platform team."             → include
"Show me everything except the orders from the platform team." → exclude
"Which tickets aren't closed?"                                 → exclude
"List the closed tickets."                                     → include
"Give me all the users who don't have MFA enabled."            → exclude
```

**Assertions.** Both the tool name *and* the arguments:

```python
expected_tools=[ToolCall(name="filter_records",
                         input_parameters={"field": "team", "value": "platform",
                                           "mode": "exclude"})]
metrics=[ToolCorrectnessMetric(threshold=1.0,
                               evaluation_params=[ToolCallParams.INPUT_PARAMETERS])]
```

**The result.** Tool selection was correct every time. The `mode` argument was set wrong intermittently — and **the failure was only visible because the suite asserted expected arguments, not just expected tool names.** A name-only assertion would have reported 100%.

**The change.** Two tools, parameters otherwise identical, polarity in the name:

```python
{
    "name": "filter_records_including_value",
    "description": "Return only records where <field> equals <value>.",
    "input_schema": {"properties": {"field": {...}, "value": {...}},
                     "required": ["field", "value"]},
},
{
    "name": "filter_records_excluding_value",
    "description": "Return all records except those where <field> equals <value>.",
    "input_schema": {"properties": {"field": {...}, "value": {...}},
                     "required": ["field", "value"]},
}
```

**The re-run.** Correct calls every time.

## Why it works when it works

Anthropic's tool-writing guidance: tools whose names reflect natural subdivisions of tasks offload agentic computation out of the agent's reasoning and back into the tool boundary, reducing the overall risk of mistakes. The agent does not have to *reason* about polarity if the name already encodes it.

## Why this failure is worth spending tool count on

Inverting flags are the worst case in tool design, and the reason is not the error rate — it is the silence.

```text
wrong argument format   → the tool errors → the agent sees it → retry → recovery
wrong polarity          → valid call → plausible results → no error → wrong answer
```

A wrong `mode` produces a structurally valid call that returns confidently wrong results. Nothing in the transcript looks broken. **That is what makes it worth spending tool count to eliminate** — unlike a malformed argument, it will not surface on its own.

## Note the order

The single tool came first. The measurement identified the specific failure. Decomposition was the response.

Running the same loop on your own tools may show the flag is handled fine on your model and your phrasing, in which case the second tool is pure cost — and tool count degrades selection accuracy on its own, so applying decomposition preemptively across a library can trade one failure mode for a worse one.

**Reserve decomposition for semantics the agent must not invert:** polarity, destructive vs read-only, scope. Do not split on every enum value — a `status` parameter with six values should stay one parameter, not become six tools. If you find yourself decomposing past two or three variants, `input_examples` is the cheaper fix.

## The A/B template

Any tool-design change, same shape.

**1. State the hypothesis as a failure you expect to see.**

> "The agent will call `search_tickets` with `team` set to a display name rather than a slug, because the schema says `string` and nothing says which."

Vague hypotheses ("better descriptions will help") produce unreadable results.

**2. Build a task set that does not name the tool.**

```text
STRONG: "Customer 9182 reported being charged three times; find the relevant
         log entries and determine whether other customers were affected."
WEAK:   "Search the payment logs for customer_id=9182."
```

The weak one names the tool call in the prompt. It measures nothing about tool design.

Cover both the success case and the case you expect to fail. 20–50 tasks is enough to start.

**3. Hold out a test set.** Split before you look at anything. Iterating on descriptions against the tasks you are measuring overfits fast, and tool descriptions are unusually easy to overfit because the feedback loop is tight.

**4. Run both variants against the same tasks, same model, same seed where available.**

```python
def ab(variant_a_tools, variant_b_tools, tasks):
    rows = []
    for t in tasks:
        a, b = run_task(t, variant_a_tools), run_task(t, variant_b_tools)
        rows.append({
            "task": t.id,
            "a_correct": a.correct,      "b_correct": b.correct,
            "a_calls": len(a.tool_calls), "b_calls": len(b.tool_calls),
            "a_tokens": a.tokens,         "b_tokens": b.tokens,
            "a_errors": a.error_types,    "b_errors": b.error_types,
        })
    return rows
```

**5. Report per-task, not just aggregate.** A change that lifts the pass rate four points while breaking two previously-passing tasks is a different decision from a clean four-point lift, and the aggregate hides it.

**6. Track more than accuracy.**

| Metric | What a change in it means |
|---|---|
| Tool calls per task | Rising = the agent is retrying or exploring; falling = better targeting |
| Invalid-parameter errors | Descriptions or examples need work |
| Redundant calls | Pagination or filtering defaults need rightsizing |
| Tokens per task | Definitions grew, or results did |
| Wrong-tool rate | Selection, separate from argument correctness — these move independently |

**7. Read the raw transcripts.** Ask the eval agent for reasoning before its tool calls, and turn on interleaved thinking if available. What the agent *omits* from its explanation matters as much as what it says.

This is where the findings you cannot design a metric for come from. Anthropic found Claude appending `2025` to web search queries unprompted, degrading results — the fix was a description change, and no aggregate metric would have named it.

## Variations worth running

| Experiment | Compare |
|---|---|
| Prefix vs suffix namespacing | `asana_search` vs `search_asana` — documented as measurable and model-dependent |
| Description length | Two sentences vs four vs eight |
| Response format | JSON vs XML vs Markdown for tool results — measurably affects performance, with no universal winner |
| Concise vs detailed returns | Anthropic's Slack tooling: `concise` used roughly a third the tokens of `detailed` |
| ID resolution | Raw UUIDs vs resolved names vs 0-indexed references |
| Consolidation | Three chained tools vs one combined tool |

Run them on your own catalog. Small description changes produce large effects — Claude Sonnet 3.5's SWE-bench Verified result came substantially from precise tool-description refinements — and the direction is not always the one you expect.

## Keep the record

```text
tools/EXPERIMENTS.md

## 2026-03-14 — filter_records polarity
Hypothesis: mode flag set wrong intermittently
Model: claude-opus-5 | Tasks: 40 (20 include / 20 exclude) | Held out: 12
Before: tool selection 40/40, mode correct 33/40
After (split into two named tools): 40/40 correct
Cost: +1 tool. Kept.

## 2026-03-21 — prefix vs suffix namespacing
Hypothesis: prefix improves selection across services
Result: no measurable difference (38/40 vs 38/40). Kept prefix for readability.
```

The null results are the valuable half. Without them the same experiment gets re-run in six months, and "we tried that, it didn't matter" is not something anyone remembers accurately.
