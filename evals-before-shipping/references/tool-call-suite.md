# A Complete Tool-Correctness Suite

Tool calling is the highest-value agent test and the most deterministic. Most of it does not need a judge model at all, which makes it cheap enough to run on every commit.

## The four case classes

A suite that only covers the first class ships an agent that calls tools for everything.

| Class | `expected_tools` | Catches |
|---|---|---|
| Should call | `[ToolCall(...)]` | The base case |
| Should **not** call | `[]` | Tool eagerness |
| Should call in order | `[a, b]` + ordering | Sequencing bugs |
| Should call several | `[a, b, c]` | Multi-tool tasks, parallel calls |

Keep should-call and should-not-call roughly balanced. A suite that is 90% should-call optimizes for an agent that always calls.

## The golden set

Keep cases as data, not as code. Every case records **why it exists**, so a future reader can delete it responsibly — suites that cannot be pruned stop being run.

```python
# tests/goldens/tool_calls.py
from deepeval.test_case import ToolCall

CASES = [
    {
        "id": "weather_simple",
        "class": "should_call",
        "input": "What's the weather in Cairo?",
        "expected_tools": [ToolCall(name="get_weather",
                                    input_parameters={"location": "Cairo, Egypt"})],
        "origin": "baseline",
    },
    {
        "id": "general_knowledge_no_tool",
        "class": "should_not_call",
        "input": "Who founded Apple?",
        "expected_tools": [],
        "origin": "2026-02: agent called search_web on trivia it knew",
    },
    {
        "id": "refund_requires_verification_first",
        "class": "ordered",
        "input": "Refund order 12345, it arrived broken.",
        "expected_tools": [
            ToolCall(name="lookup_order", input_parameters={"order_id": "12345"}),
            ToolCall(name="issue_refund", input_parameters={"order_id": "12345"}),
        ],
        "ordered": True,
        "origin": "2026-01 incident: refund issued before order existence check",
    },
    {
        "id": "ambiguous_city_asks_rather_than_guesses",
        "class": "should_not_call",
        "input": "What's the weather in Springfield?",
        "expected_tools": [],
        "origin": "2026-03: agent silently picked Springfield, IL",
    },
]
```

The `origin` field is not documentation. A case with no recorded reason cannot be deleted safely, so it accumulates, and a suite nobody can prune becomes one nobody runs.

## Assert arguments, not just names

This is the highest-value line in the file.

```python
from deepeval.metrics import ToolCorrectnessMetric, ArgumentCorrectnessMetric
from deepeval.test_case import LLMTestCase, ToolCallParams

SELECTION = ToolCorrectnessMetric(threshold=1.0)

ARGUMENTS = ToolCorrectnessMetric(
    threshold=1.0,
    evaluation_params=[ToolCallParams.INPUT_PARAMETERS],
)

ARGS_JUDGED = ArgumentCorrectnessMetric(threshold=0.8)   # referenceless, LLM-based
```

A name-only assertion reports 100% on an agent that picks the right tool and sets a polarity flag backwards — a call that is structurally valid, raises no error, and returns confidently wrong results. `tool-design/references/naming-experiments.md` walks through exactly that case.

Use `ToolCorrectnessMetric` with `INPUT_PARAMETERS` where you know the expected arguments; `ArgumentCorrectnessMetric` where the values can't be predetermined (a generated summary, a timestamp, a free-text query).

**`threshold=1.0` on tool selection.** Calling the wrong tool is not 70% correct.

## Tuning strictness

| Option | Use when | Cost of overusing |
|---|---|---|
| `should_consider_ordering=True` | Order is a real requirement — verify before refunding | Breaks on every valid alternative route |
| `should_exact_match=True` | Names *and* parameters must match exactly | Brittle against harmless argument variation |
| `evaluation_params=[ToolCallParams.INPUT_PARAMETERS]` | Almost always | None — use it |
| `available_tools=[...]` | You want "called a valid tool, but not the best one" caught | Adds an LLM judgment and its cost |

`available_tools` makes the metric additionally judge whether the called tools were the *most optimal* choice from the catalog, and the final score is the minimum of both. That is the check that catches an agent using `search_all_records` when `get_record_by_id` existed.

Apply ordering per case, not globally:

```python
def metrics_for(case):
    m = [ToolCorrectnessMetric(threshold=1.0,
                               should_consider_ordering=case.get("ordered", False)),
         ToolCorrectnessMetric(threshold=1.0,
                               evaluation_params=[ToolCallParams.INPUT_PARAMETERS])]
    if case["class"] != "should_not_call":
        m.append(ArgumentCorrectnessMetric(threshold=0.8))
    return m
```

Note the last two lines: `ArgumentCorrectnessMetric` on a case with no tool calls has nothing to judge.

## The runner

```python
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase

@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_tool_calls(case):
    output = my_agent(case["input"])
    assert_test(
        LLMTestCase(
            input=case["input"],
            actual_output=output.text,
            tools_called=output.tools_called,
            expected_tools=case["expected_tools"],
        ),
        metrics=metrics_for(case),
    )
```

```bash
deepeval test run tests/test_tool_calls.py
deepeval test run tests/test_tool_calls.py -c     # cache: don't rerun passing cases
deepeval test run tests/test_tool_calls.py -i     # ignore errors, finish the run
```

Each `assert_test()` needs at least one non-flaky metric with a threshold, or nothing can fail.

## Multi-tool tasks

Where sequencing and argument threading actually break — the second call's arguments come from the first call's result.

```python
{
    "id": "cross_reference_customer_and_orders",
    "input": "Has customer jane@acme.com had any failed payments this quarter?",
    "expected_tools": [
        ToolCall(name="lookup_customer", input_parameters={"email": "jane@acme.com"}),
        ToolCall(name="list_payments",
                 input_parameters={"customer_id": "CUS-4410", "status": "failed"}),
    ],
    "ordered": True,
    "origin": "2026-02: agent passed the email into customer_id",
}
```

That origin note is the classic failure: the agent has the id from the first result and passes the email anyway. Only an argument assertion catches it.

## Negative cases worth having

Beyond "answer from knowledge":

```text
ambiguous input        → should ask, not guess    ("weather in Springfield?")
out of scope           → should decline           ("book me a flight" with no flight tool)
missing information    → should ask for it        ("refund my order" with no order id)
destructive without    → should confirm first     ("delete all my data")
  confirmation
already-answered       → should not re-call       (follow-up answerable from context)
```

The last one is underrated. An agent that re-calls the same tool on every follow-up turn doubles cost and is invisible to a pass/fail suite that only checks the answer.

## Metrics that run in production

Split the list by environment. Reference-based metrics need ground truth that live traffic does not have.

| Metric | Dev | Production |
|---|---|---|
| `ToolCorrectnessMetric` | Yes | No — needs `expected_tools` |
| `ArgumentCorrectnessMetric` | Yes | **Yes** — referenceless |
| `TaskCompletionMetric` | Yes | **Yes** — referenceless |

```python
DEV_METRICS = [ToolCorrectnessMetric(threshold=1.0), ArgumentCorrectnessMetric(threshold=0.8)]
PROD_METRICS = [ArgumentCorrectnessMetric(threshold=0.8)]
```

Sample production rather than scoring everything — judge calls cost real money, and a 1–5% sample is enough to catch a regression.

## Two suites, opposite targets

**Regression** — everything the agent already handles. Target near 100%. Gate CI on this one; a drop means you broke something.

**Capability** — things it struggles with. Should *start* at a low pass rate. A capability suite passing at 95% on day one was too easy to be informative.

Promote a capability case into the regression suite once it is reliably solved. That promotion is the visible record that the agent got better.

## Reading a failure

A failed case is not automatically a broken agent. In order of likelihood:

1. **The case is wrong.** `expected_tools` encodes an assumption that is no longer true, or was never true.
2. **The agent found a valid alternative route.** Common with ordering enabled. Relax the assertion or accept the route.
3. **The tool is wrong.** Description, schema, or naming. Go to `tool-design`.
4. **The agent is wrong.** The rarest of the four.

Read `.reason` on every failure before changing anything — every metric returns `.score`, `.reason`, and `.is_successful()`, and `verbose_mode=True` shows the judge's working. A 0% pass rate on a frontier model almost always means the task or the grader is wrong, not the model.
