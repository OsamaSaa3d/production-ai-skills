# Why Not Framework Agent Abstractions

This is not a claim that frameworks are badly built. It is a claim about what you give up, mechanism by mechanism, and when that trade is worth making.

The short version: the abstraction sits between you and a loop you can read in forty lines (`agent-loop.md`), and it takes four things with it — control flow, error visibility, telemetry, and the schedule on which your code changes.

## Failure mode 1: exceptions become prompt text

This is the most expensive one, because it converts a loud failure into a quiet one.

Your tool raises `PermissionError: token expired`. The native pattern puts a structured error in the tool result and the exception is yours to log, alert on, and count:

```python
try:
    result = registry[name](**args)
except Exception as e:
    log.exception("tool_failed", tool=name, args=args)     # you see this
    result = {"error": f"{type(e).__name__}: {e}"}          # the model sees this
```

The framework pattern catches the exception internally, stringifies it into the observation, and continues. The model reads "PermissionError: token expired", tries a different approach, maybe succeeds, and the run returns a plausible answer. Nothing surfaced. Your error rate looks fine. The expired token is discovered a week later by a human.

Both designs feed the error to the model — that part is correct and the native loop does it too. The difference is whether *you* also get it. Check what your framework does with `handle_parsing_errors` and its tool-error hook; the defaults usually favor the run completing over you finding out.

## Failure mode 2: the loop you cannot change

Stopping conditions worth having: iteration cap, cost cap, wall-clock cap, repeated-identical-call detection, and an in-band nudge when the model is stuck. That is the list from `agent-loop.md`, and all five are a few lines each when you own the `for`.

Inside an `AgentExecutor`-shaped abstraction you get `max_iterations` and `max_execution_time` as constructor arguments, and everything else requires a callback, a subclass, or a custom executor. The cost cap in particular tends not to be expressible, because the framework does not track per-run token usage in a form you can gate on — and cost, not iteration count, is what actually hurts.

The tell that you have hit this wall: you are reading framework source to find out where to inject something the loop above does in one line.

## Failure mode 3: the prompt you didn't write

Agent abstractions assemble a system prompt from templates — a ReAct scaffold, format instructions, tool descriptions rendered into text. On a model with native tool calling, that scaffold is redundant with the API's own tool-use system prompt, and it competes with your instructions for attention.

Two concrete consequences:

- **You cannot audit what was sent.** Debugging "why did it call that tool" requires the exact prompt. If it is assembled three layers down from a template you have not read, you are guessing.
- **Model migrations get harder.** When a new model changes how it responds to a prompt pattern, you need to change the pattern. If the pattern is the framework's, you wait for the framework.

Turn on whatever verbose/callback mode dumps the raw request and read it once. The gap between what you thought you were sending and what went on the wire is usually instructive.

## Failure mode 4: a second `strict` with its own default

The guarantee in this skill rests on one field reaching the provider. Wrappers frequently expose their own `strict` flag with its own default, and some drop the field when converting your schema into their tool type.

```text
Two places the guarantee can be off, only one of which you wrote.

FrameworkTool.from_function(fn, strict=???)   <- framework default
   └─> provider payload: {"strict": ???}      <- what actually shipped
```

If you use a wrapper, verify once at the wire: log the outgoing payload, or check that the tool comes back in the response marked strict. "I set `strict=True` in the decorator" is not evidence.

## Failure mode 5: ReAct text parsing under a native-tool-calling model

`create_react_agent` and its relatives ask the model to emit `Thought: / Action: / Action Input:` and parse it with string matching. This predates native tool calling and is strictly worse than it: no constrained decoding, no schema validation, no protection against an invented tool name — plus a parse step that fails on the model's own formatting variation.

The framework's answer to parse failures is usually a retry with a "you formatted that wrong" message appended. You are paying tokens to correct a problem the API removed.

If you are on a model with tool support, there is no version of this that wins. If you are on a model without it, write the parser explicitly so you can see it fail.

## Failure mode 6: telemetry that doesn't join

You already have logging, tracing, and metrics. The framework has callbacks, handlers, or its own tracing product. Joining the two means writing an adapter — and the thing you most want, per-run token cost attributed to a request id, is often the hardest to get out, because it accumulates inside the executor.

The native loop gives it to you as a local variable.

## The upgrade treadmill

Provider APIs are versioned and conservative about breaking changes. Framework agent APIs have historically moved faster than the providers underneath them — `initialize_agent` → `AgentExecutor` → `create_react_agent` → graph-based constructions, each a migration for code that calls one endpoint.

The asymmetry is the argument: your tool-calling code is coupled to an interface that changes rarely, unless you insert one that changes often.

## When a framework is the right call

These are real, and they are narrow:

- **Prototyping you will throw away within days.** Speed to first result beats everything.
- **You need a specific feature and have priced building it.** Durable checkpointing and resumable state machines (LangGraph's case) are genuinely non-trivial. Evaluate honestly: the feature, not the framework's marketing.
- **It is already load-bearing.** Removing a framework from a working system is a migration with no user-visible benefit. Don't.
- **Team convention.** A team fluent in one framework shipping consistent code beats every engineer hand-rolling a slightly different loop. This is a real engineering argument.

## Migrating off one

If you decide to remove it, do it in this order — each step is independently shippable and independently revertable:

1. **Log the outgoing payload.** Find out what the framework is actually sending. This alone often changes the plan.
2. **Extract the tool functions.** They are plain functions under whatever decorator. Build a `dict[str, Callable]` registry.
3. **Lift the schemas.** Copy the generated JSON Schema out of the framework's tool objects; make sure `strict: true` and `additionalProperties: false` survive the move.
4. **Write the loop.** `agent-loop.md`, forty lines.
5. **Run both against the same eval suite.** `evals-before-shipping`. Same cases, same model, compare pass rate, tokens per task, and tool calls per task.
6. **Cut over when the native version matches or beats it.** If it doesn't, the framework was doing something — find out what, and decide whether you want it.

Step 5 is the one people skip, and it is the only one that makes this a decision rather than a preference.
