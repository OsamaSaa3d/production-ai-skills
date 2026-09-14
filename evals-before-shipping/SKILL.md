---
name: evals-before-shipping
description: Use this skill whenever you are writing tests for an LLM application, agent, or RAG pipeline — or whenever you are about to change a prompt, swap a model, add or rename a tool, or modify retrieval and need to know whether it helped. Use it when the user says an LLM system "feels worse," "seems better," or asks whether a change was an improvement. Use it when asked to check whether an agent calls the right tools, whether a RAG pipeline retrieves and grounds correctly, or whether an agent completes its task. Build the eval suite with DeepEval and run it in CI. Do not hand-roll scoring logic for things DeepEval already has a metric for.
---

# Eval Suites for LLM Apps

## Core principle

An LLM app without an eval suite has no tests. Build the suite with `deepeval`, run it under pytest, gate CI on it.

Two rules that govern everything below:

**Cap the suite at 5 metrics** — 2-3 generic system metrics (tool correctness, faithfulness) plus 1-2 custom `GEval` criteria for your use case. More metrics means less signal, not more.

**Reference-based metrics are dev-only.** `ToolCorrectnessMetric` and `ContextualRecallMetric` need ground truth, so they cannot run in production. Referenceless metrics (`AnswerRelevancyMetric`, `FaithfulnessMetric`, `ArgumentCorrectnessMetric`, `TaskCompletionMetric`) work on live traffic.

## Setup

```bash
pip install deepeval
export OPENAI_API_KEY=...   # the judge model, not your app's model
```

Judge model is configurable — `deepeval set-gemini`, `deepeval set-ollama --model=...`, `deepeval set-azure-openai ...`, or pass `model=` per metric. Anthropic, LiteLLM, and custom `DeepEvalBaseLLM` subclasses all work.

All metrics score 0-1, **higher is better**, and pass when `score >= threshold` (default `0.5`). Every metric returns `.score`, `.reason`, and `.is_successful()`.

## Did the agent call the right tools?

This is the highest-value agent test and it is mostly deterministic. Two metrics, different jobs:

`ToolCorrectnessMetric` — **reference-based.** Compares `tools_called` against `expected_tools`. Use when you know which tools the task requires.

`ArgumentCorrectnessMetric` — **referenceless, LLM-based.** Judges whether the arguments were logically derived from the input. Use when argument values can't be predetermined.

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.metrics import ToolCorrectnessMetric, ArgumentCorrectnessMetric

test_case = LLMTestCase(
    input="What's the weather in Cairo and should I bring an umbrella?",
    actual_output="It's 31°C and clear — no umbrella needed.",
    tools_called=[
        ToolCall(name="get_weather", input_parameters={"location": "Cairo, Egypt"}),
    ],
    expected_tools=[
        ToolCall(name="get_weather", input_parameters={"location": "Cairo, Egypt"}),
    ],
)

evaluate(
    test_cases=[test_case],
    metrics=[
        ToolCorrectnessMetric(threshold=1.0),   # tool selection is binary — demand perfection
        ArgumentCorrectnessMetric(threshold=0.8),
    ],
)
```

Tune strictness with:

- `should_consider_ordering=True` — the tools must be called in the expected order. Only set this when order genuinely matters (verify identity *before* issuing a refund). Otherwise it makes the test brittle.
- `should_exact_match=True` — names and parameters must match exactly.
- `evaluation_params=[ToolCallParams.INPUT_PARAMETERS]` — scores the proportion of correct parameters instead of pass/fail on name alone.
- `available_tools=[...]` — the metric additionally uses an LLM to judge whether the called tools were the *most optimal* choice from the catalog. Final score is the minimum of both. Use this to catch "called a valid tool, but the wrong one."

**Set `threshold=1.0` on `ToolCorrectnessMetric`.** Calling the wrong tool is not 70% correct.

### The test set that actually matters: negative cases

Tool-calling suites fail in production because they only test that the agent calls tools when it should. Test the other direction or you will ship an agent that calls tools for everything.

```python
should_call = LLMTestCase(
    input="What's the weather in Cairo?",
    actual_output="It's 31°C and clear.",
    tools_called=[ToolCall(name="get_weather", input_parameters={"location": "Cairo, Egypt"})],
    expected_tools=[ToolCall(name="get_weather", input_parameters={"location": "Cairo, Egypt"})],
)

should_not_call = LLMTestCase(
    input="Who founded Apple?",
    actual_output="Steve Jobs, Steve Wozniak, and Ronald Wayne.",
    tools_called=[],        # correct behavior: answer from knowledge
    expected_tools=[],
)
```

Keep the two classes roughly balanced. A suite that is 90% should-call optimizes for an agent that always calls.

## RAG: score the retriever and the generator separately

Five metrics split across the two components. When RAG output is wrong, this split tells you *which half* is broken.

**Retriever** — did we fetch the right chunks?
- `ContextualRelevancyMetric` — is the retrieved context relevant to the query? (referenceless)
- `ContextualPrecisionMetric` — are relevant chunks ranked above irrelevant ones? (needs `expected_output`)
- `ContextualRecallMetric` — did we retrieve everything needed? (needs `expected_output`, **reference-based**)

**Generator** — given the chunks, did we answer well?
- `AnswerRelevancyMetric` — does the answer address the question? (referenceless)
- `FaithfulnessMetric` — is the answer grounded in the retrieved context, i.e. no hallucination? (referenceless)

```python
from deepeval.metrics import (
    ContextualRelevancyMetric, ContextualPrecisionMetric, ContextualRecallMetric,
    AnswerRelevancyMetric, FaithfulnessMetric,
)

test_case = LLMTestCase(
    input="What is our refund window for enterprise customers?",
    actual_output=rag_pipeline(query),          # your app
    retrieval_context=retrieved_chunks,          # list[str] — the chunks you actually retrieved
    expected_output="Enterprise customers have 60 days.",  # only needed by precision/recall
)

evaluate(
    test_cases=[test_case],
    metrics=[
        ContextualRelevancyMetric(threshold=0.7),
        ContextualRecallMetric(threshold=0.8),
        FaithfulnessMetric(threshold=0.9),       # hallucination is the worst failure — set high
        AnswerRelevancyMetric(threshold=0.7),
    ],
)
```

**Diagnostic pattern.** Low retriever scores with high generator scores means fix chunking, embeddings, or reranking. High retriever scores with low `FaithfulnessMetric` means fix the generation prompt — the context was there and the model ignored it. Low on both means start with the retriever; the generator can't fix what it never received.

Start with `FaithfulnessMetric` and `AnswerRelevancyMetric` if you only pick two. They are referenceless, so the same two run in production monitoring unchanged.

## Agent trajectory metrics

These read the **complete ordered trace**, so they require tracing via `@observe()` and run through `evals_iterator()` rather than `evaluate()`.

- `TaskCompletionMetric` — did the agent actually accomplish the task? (referenceless; the headline metric)
- `StepEfficiencyMetric` — did it avoid redundant steps?
- `PlanAdherenceMetric` — did it follow its own plan?
- `PlanQualityMetric` — was the plan logical and complete?

```python
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.metrics import TaskCompletionMetric
from deepeval.tracing import observe

@observe()
def support_agent(user_message: str):
    @observe()
    def lookup_order(order_id): ...
    @observe()
    def issue_refund(order_id, amount): ...
    ...

dataset = EvaluationDataset(goldens=[
    Golden(input="I want a refund for order 12345, it arrived broken"),
    Golden(input="Where is my order 67890?"),
])

for golden in dataset.evals_iterator(metrics=[TaskCompletionMetric(threshold=0.7)]):
    support_agent(golden.input)
```

For component-level metrics, attach them to the specific span that makes the decision and build the test case at runtime:

```python
from deepeval.tracing import observe, update_current_span

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

Use trajectory metrics for overall execution quality; use component metrics to pinpoint which decision broke.

## Custom criteria with GEval

For anything domain-specific that no built-in metric covers, write the criterion in plain language.

```python
from deepeval.metrics import GEval
from deepeval.test_case import SingleTurnParams

policy_grounding = GEval(
    name="PolicyGrounding",
    criteria=(
        "Determine whether the actual output's claims about company policy "
        "are supported by the retrieval context. Penalize any policy statement "
        "not traceable to the context."
    ),
    evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
    threshold=0.8,
)
```

Use `GEval` for subjective criteria (tone, reasoning clarity, correctness). Use `DAGMetric` when you need a deterministic decision tree — check format *before* judging tone, for example. Start with `GEval`; move to `DAG` when you need control or determinism.

## Run it in CI

`deepeval test run` is the pytest integration. Use `assert_test` so failures fail the build.

```python
# tests/test_agent.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.metrics import ToolCorrectnessMetric, FaithfulnessMetric

@pytest.mark.parametrize("case", load_test_cases())   # your golden set
def test_agent(case):
    output = my_agent(case.input)
    assert_test(
        LLMTestCase(
            input=case.input,
            actual_output=output.text,
            tools_called=output.tools_called,
            expected_tools=case.expected_tools,
            retrieval_context=output.chunks,
        ),
        metrics=[
            ToolCorrectnessMetric(threshold=1.0),
            FaithfulnessMetric(threshold=0.9),
        ],
    )
```

```bash
deepeval test run tests/test_agent.py
deepeval test run tests/test_agent.py -c    # use cache; don't rerun passing cases
deepeval test run tests/test_agent.py -i    # ignore errors, finish the run
```

Two flags worth knowing per metric:

- `flaky=True` — the score is still computed and reported, but a failure does not fail the test case. Use for metrics you know are noisy rather than deleting them.
- `threshold=None` — score-only mode. Computed and tracked, no pass/fail opinion. Use for metrics you're still calibrating.

Each `assert_test()` needs at least one non-flaky metric with a threshold, or nothing can fail.

## Two suites, opposite targets

Keep these separate and run both.

**Regression suite** — everything the system already handles. Target near 100%. A drop means you broke something. Gate CI on this one.

**Capability suite** — things the system struggles with. Should *start at a low pass rate*; it's the hill to climb. A capability suite passing at 95% on day one was too easy to be informative.

When a capability task becomes reliably solved, move it into the regression suite.

## Pitfalls

**Grading the path instead of the outcome.** Asserting exact tool sequences breaks whenever the agent finds a valid alternative route. Use `should_consider_ordering=True` only where order is a real requirement, and prefer outcome checks.

**Only testing the positive class.** Covered above. Balance should-call against should-not-call.

**Uncalibrated LLM judges.** Model-based metrics need checking against human labels before you trust them. Turn on `verbose_mode=True` and read the `.reason` output on a sample of cases.

**One judge scoring everything.** Give each dimension its own metric. A single `GEval` asked to score correctness, tone, and grounding at once produces mush.

**Not reading the results.** `.reason` exists on every metric. A score you haven't investigated is not a result — the failure might be a broken test case rather than a broken agent. A 0% pass rate on a frontier model usually means the task or grader is wrong.

**Reference-based metrics in production.** `ToolCorrectnessMetric` and `ContextualRecallMetric` need ground truth that live traffic doesn't have. Split your metric list by environment.

**Waiting for a big test set.** 20-50 cases pulled from real failures, your bug tracker, and your support queue is enough to start. The suite gets harder to build the longer you wait.

## References

- `references/tool-call-suite.md` — full tool-correctness suite including negative cases, ordering, and multi-tool tasks
- `references/rag-suite.md` — complete RAG eval with retriever/generator diagnosis and threshold tuning
- `references/tracing-setup.md` — `@observe()` instrumentation for existing agents without restructuring them
- `references/custom-metrics.md` — `GEval` and `DAGMetric` patterns, judge calibration procedure
- `references/ci-integration.md` — CI config, caching, handling flaky metrics, cost control