# Instrumenting an Existing Agent

Trajectory metrics — `TaskCompletionMetric`, `StepEfficiencyMetric`, `PlanAdherenceMetric`, `PlanQualityMetric` — read the **complete ordered trace**, not a single input/output pair. That means tracing, and tracing is where people assume they need to restructure the agent.

They don't. `@observe()` is a decorator. You add it to functions that already exist.

## The minimum

```python
from deepeval.tracing import observe

@observe()
def support_agent(user_message: str) -> str:
    ...

@observe()
def lookup_order(order_id: str) -> dict:
    ...

@observe()
def issue_refund(order_id: str, amount: float) -> dict:
    ...
```

Nested calls nest in the trace automatically. Decorate the entry point and each tool; that is enough for `TaskCompletionMetric`.

## What to decorate, and what not to

| Decorate | Skip |
|---|---|
| The agent entry point | Pure helpers (formatters, parsers) |
| Each tool function | Anything called hundreds of times per run |
| The retrieval step in a RAG pipeline | Logging and metrics plumbing |
| The step that decides which tool to call | Getters and property accessors |
| A planning step, if one exists | |

Over-instrumenting produces traces too noisy to read and too large to judge cheaply. Start with the entry point and the tools; add spans when a diagnosis needs them.

## Running trajectory metrics

Trajectory metrics go through `evals_iterator()`, not `evaluate()` — the iterator drives your agent so the trace exists to be scored.

```python
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.metrics import TaskCompletionMetric

dataset = EvaluationDataset(goldens=[
    Golden(input="I want a refund for order 12345, it arrived broken"),
    Golden(input="Where is my order 67890?"),
])

for golden in dataset.evals_iterator(metrics=[TaskCompletionMetric(threshold=0.7)]):
    support_agent(golden.input)
```

`TaskCompletionMetric` is referenceless — no `expected_output` needed — which is why it is the headline agent metric and why it also runs in production.

## Component-level metrics

Attach a metric to the specific span that makes a decision, and build the test case at runtime:

```python
from deepeval.tracing import observe, update_current_span
from deepeval.test_case import LLMTestCase
from deepeval.metrics import ToolCorrectnessMetric

@observe(metrics=[ToolCorrectnessMetric(threshold=1.0)])
def choose_tool(user_message: str):
    result = llm_decide(user_message)
    update_current_span(test_case=LLMTestCase(
        input=user_message,
        actual_output=str(result),
        tools_called=result.tools_called,
        expected_tools=EXPECTED[user_message],
    ))
    return result
```

**Trajectory metrics tell you the run failed. Component metrics tell you which decision broke it.** Use both: `TaskCompletionMetric` at the top, `ToolCorrectnessMetric` on the selection span, a RAG metric on the retrieval span.

## Retrofitting without restructuring

Three patterns for agents you'd rather not edit.

**Wrap at the registry.** If tools are dispatched through a dict, instrument once:

```python
def traced(fn):
    return observe(name=fn.__name__)(fn)

TOOL_REGISTRY = {name: traced(fn) for name, fn in RAW_TOOLS.items()}
```

Every tool instrumented, zero changes to the tool functions.

**Wrap at the client.** If the agent calls the API through one helper, decorate the helper. You lose per-tool granularity but get the full model-call sequence for free.

**Decorate the methods, not the class.** For a class-based agent, decorate `run()` and the tool methods. There is no need to restructure the class.

## Traces the metrics can actually judge

Three things make the difference between a trace that diagnoses and one that is noise.

**Return values a judge can read.** A span returning a 4,000-row DataFrame gives the judge nothing usable and costs tokens. Return a summary:

```python
@observe()
def search_logs(query: str) -> dict:
    rows = db.search(query)
    return {"count": len(rows), "sample": rows[:5], "query": query}
```

**Errors in the trace, not swallowed.** An exception caught and converted to a bland string makes a failed run look successful to `TaskCompletionMetric`. Let the span see the failure:

```python
@observe()
def issue_refund(order_id: str, amount: float) -> dict:
    try:
        return {"ok": True, "refund_id": api.refund(order_id, amount)}
    except RefundError as e:
        return {"ok": False, "error": str(e)}     # visible in the trace
```

**Name spans after what they do.** `@observe(name="retrieve_policy_docs")` reads better in a trace than `_do_step_3`, and the judge reads those names.

## Local vs hosted

`@observe()` works without any platform account — traces are built in-process and consumed by the metrics. Hosted collection adds dashboards and history.

If you cannot send traces off-box, keep traces local and export your own summary rows:

```python
{"run_id": ..., "input": ..., "spans": [{"name": "lookup_order", "ms": 82, "ok": True}, ...],
 "task_completion": 0.86, "tokens": 12_400, "cost_usd": 0.07}
```

That is enough for regression tracking in your existing observability stack.

## Cost control

Trajectory metrics judge the *whole trace*, so they are the most expensive metrics in the suite — a long agent run is a large judge prompt.

- **Use a cheaper judge model** for trajectory metrics. Judging "did this run accomplish the task" does not need your most expensive model. Calibrate it against human labels first, then keep it. `deepeval set-gemini`, `deepeval set-ollama --model=...`, `deepeval set-azure-openai`, or `model=` per metric.
- **Keep span returns small.** The single biggest lever, and it makes traces more readable too.
- **Run trajectory metrics on a subset.** Component metrics on every case, trajectory metrics on 20–30 representative ones.
- **Cache passing cases** in CI with `deepeval test run -c`.

## Traces in production

The same instrumentation serves production monitoring, with the metric list swapped:

```python
DEV_METRICS  = [TaskCompletionMetric(), StepEfficiencyMetric(),
                ToolCorrectnessMetric(threshold=1.0)]     # last one needs ground truth
PROD_METRICS = [TaskCompletionMetric(threshold=0.7)]      # referenceless
```

Sample rather than scoring everything, and alert on the rate. Beyond the metrics, the traces themselves are the highest-value artifact you get from this — a production failure with a full span tree is a five-minute diagnosis instead of an afternoon.

## Common problems

**"The metric says the trace is empty."** The entry point isn't decorated, or the agent runs in a subprocess or thread the tracer doesn't follow. Decorate the outermost function that runs in-process.

**"Scores are wildly inconsistent run to run."** Span returns are too large or too noisy for the judge to read consistently. Summarize them.

**"Everything passes but the agent is obviously bad."** `TaskCompletionMetric` infers the task from the trace. If the trace does not contain enough to tell success from failure — tools that return `{"ok": true}` with no substance — the judge has nothing to judge. Make span returns informative.

**"It's too slow."** Trajectory metrics on every case in CI is the usual cause. Subset them, cache passing cases, and use a cheaper judge.
