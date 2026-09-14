# The Tool Optimization Harness, End to End

Every remedy in the tool-design skill costs something — tool count, tokens, latency, or complexity. This loop is what makes them safe to apply: write the natural tool first, measure, then fix the failure the measurement names.

## The seven steps

1. **Prototype** the tools. Wire them into a local MCP server or pass them directly to the API.
2. **Generate realistic tasks.** Multiple tool calls, realistic data, and never name the tool in the prompt.
3. **Run each task in a simple `while` loop** — model call, tool call, repeat. One loop per task. Direct API calls, no framework.
4. **Ask the eval agent for reasoning before its tool calls.** Turn on interleaved thinking if available. This tells you *why* it picked a tool.
5. **Track more than accuracy**: tool calls per task, errors by type, tokens, runtime.
6. **Read the raw transcripts.** What the agent omits matters as much as what it says.
7. **Hold out a test set** so you don't overfit descriptions to your examples.

## Step 2: the tasks are the hard part

A weak task set makes every subsequent step meaningless.

```text
STRONG — the agent has to figure out which tools and in what order:
  "Customer 9182 reported being charged three times for their October
   subscription. Find the relevant log entries and determine whether other
   customers were affected by the same issue."

WEAK — names the tool call in the prompt:
  "Search the payment logs for customer_id=9182."
```

The weak version measures whether the agent can copy a parameter out of a sentence. Everything you want to know — selection, argument construction, sequencing, when to stop — is only visible when the task is phrased the way a user would phrase it.

Sources for real tasks, in descending order of value: production transcripts where the agent failed, your support queue, your bug tracker, and only then synthesized ones. 20–50 cases pulled from real failures is enough to start, and the suite gets harder to build the longer you wait.

Cover four classes deliberately:

| Class | Why |
|---|---|
| Should call tool X | The base case |
| Should call **no** tool | Otherwise you ship an agent that calls tools for everything |
| Should call X then Y | Sequencing and argument threading |
| Should recognize it can't | Missing data, out of scope — does it say so or invent? |

Keep should-call and should-not-call roughly balanced. A suite that is 90% should-call optimizes for an agent that always calls.

## Step 3: the runner

```python
def run_task(task, tools, registry, max_iters=10):
    messages = [{"role": "user", "content": task.prompt}]
    calls, errors, tokens = [], [], 0

    for _ in range(max_iters):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools, tool_choice="auto",
        )
        tokens += resp.usage.total_tokens
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return TaskRun(task.id, msg.content, calls, errors, tokens)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            calls.append(ToolCall(name=tc.function.name, input_parameters=args))
            out = execute(tc, registry)
            if "error" in out:
                errors.append((tc.function.name, classify_error(out["error"])))
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(out)})

    return TaskRun(task.id, None, calls, errors, tokens, hit_cap=True)
```

Direct API calls. The point of the harness is to see exactly what the tools do; a framework between you and the payload defeats it.

## Step 4: ask for reasoning

```python
SYSTEM_EVAL = """You have access to tools. Before each tool call, state in one
sentence why you are calling that tool and what you expect back. After the
result, state in one sentence whether it was what you expected.

If a tool description was unclear or a parameter was ambiguous, say so
explicitly — that feedback is the point of this run."""
```

This turns a pass/fail into a diagnosis. "I called `search_logs` because I expected it to return the log lines, but it returned only counts" names the exact description defect in one sentence. Use this system prompt only in the harness, not in production — it costs tokens and changes behavior.

## Step 5: the metrics

Wire it to `evals-before-shipping` rather than hand-rolling scoring:

```python
from deepeval.metrics import ToolCorrectnessMetric, ArgumentCorrectnessMetric
from deepeval.test_case import LLMTestCase, ToolCall, ToolCallParams

def to_test_case(run, task):
    return LLMTestCase(
        input=task.prompt,
        actual_output=run.final_text or "",
        tools_called=run.calls,
        expected_tools=task.expected_tools,
    )

metrics = [
    ToolCorrectnessMetric(threshold=1.0),            # selection is binary
    ToolCorrectnessMetric(threshold=1.0,
        evaluation_params=[ToolCallParams.INPUT_PARAMETERS]),   # arguments too
    ArgumentCorrectnessMetric(threshold=0.8),        # referenceless
]
```

**Assert arguments, not just names.** This is the single most important line in the file. The include/exclude experiment in `naming-experiments.md` found a failure that a name-only assertion reported as 100% correct — and polarity bugs are exactly the class that never surfaces on its own.

Set `should_consider_ordering=True` only where order is a genuine requirement (verify identity *before* issuing a refund). Otherwise it makes the suite brittle against valid alternative routes.

Track alongside the pass rate:

| Signal | Reading |
|---|---|
| Tool calls per task | Rising = retrying or exploring; falling = better targeting |
| Invalid-parameter errors | Descriptions or `input_examples` need work |
| Redundant identical calls | Pagination or filtering defaults are wrong |
| Wrong-tool rate | Selection, independent of argument correctness |
| Tokens per task | Definitions grew, or results did — check `result_tokens` per call |
| Tasks hitting the iteration cap | The agent cannot finish; usually a missing tool or an opaque error |

## Step 6: read the transcripts

Metrics tell you a task failed. Transcripts tell you why, and they produce findings no metric was designed to catch.

Read every failure, and a sample of the passes. What to look for:

- **A tool called and its result ignored.** The return format isn't answering the question.
- **The same call repeated with identical arguments.** The result doesn't say what the agent needed, or the error doesn't steer.
- **A long preamble before a simple call.** The agent is uncertain which tool to use; two descriptions overlap.
- **Arguments the agent clearly guessed.** A convention that needs `input_examples`.
- **Unprompted additions to arguments.** Anthropic found Claude appending `2025` to web search queries unprompted, degrading results. The fix was a description change, and no aggregate metric would have named it.

## Step 7: hold out a test set

Split before you look at anything, and keep the split stable.

```python
random.Random(42).shuffle(tasks)
dev, test = tasks[:40], tasks[40:]      # iterate on dev, report on test
```

Tool descriptions are unusually easy to overfit because the feedback loop is tight — you change one sentence, re-run, see a jump. Iterating against the tasks you report on produces descriptions tuned to twelve specific phrasings.

Report the test number. Look at it rarely.

## Diagnosing from the numbers

| Symptom in the metrics | Likely cause | Fix |
|---|---|---|
| Wrong tool chosen | Names overlap, or namespacing unclear | Rename, namespace, remove near-identical pairs |
| Right tool, wrong arguments (conventions) | Schema can't express your formats | `input_examples` |
| Right tool, wrong arguments (polarity, scope) | Semantics in a parameter | Decompose into named tools |
| Many invalid-parameter errors | Descriptions underspecified | Rewrite descriptions; add examples |
| Many redundant calls | Defaults too narrow, or results unhelpful | Rightsize pagination; return higher-signal fields |
| Tokens dominated by definitions | Catalog too large upfront | `defer_loading` + tool search |
| Tokens dominated by results | Results flooding context | Filtering, pagination, or programmatic calling |
| Tasks hitting the iteration cap | Missing capability, or opaque errors | Add the tool; make errors steer |
| Agent never uses a tool | Description doesn't say *when* to use it | Rewrite for trigger conditions |

## Re-run on every change

The loop is not a one-time exercise. Re-run when you:

- Change any tool name, description, or schema
- Add or remove a tool
- Change a model — **especially on a downgrade**. Selection accuracy degrades fastest on small models, so a catalog a large model handles fine may be past the cliff for a cheaper one. See `model-selection`.
- Enable `defer_loading`, programmatic calling, or `input_examples`
- Change a tool's return format

A tool suite validated on one model is not validated on another. Pin the model alongside the tool definitions and treat a model change as a tool change requiring a full re-run.

## What "done" looks like

- [ ] 20–50 tasks, phrased as users phrase them, none naming a tool
- [ ] Should-call and should-not-call roughly balanced
- [ ] Held-out test set, split before any iteration
- [ ] Arguments asserted, not just tool names
- [ ] Wrong-tool rate tracked separately from pass rate
- [ ] `result_tokens` logged per tool call
- [ ] Transcripts read for every failure
- [ ] Each applied remedy traceable to a measured failure — and re-measured after
