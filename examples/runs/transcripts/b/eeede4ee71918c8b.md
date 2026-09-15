[init] cwd=C:\tmp\skills-eval\arm-b\t02-r0 model=claude-sonnet-5 mcp=[] plugins=[] skills=['agent-vs-workflow-decision', 'context-and-memory', 'evals-before-shipping', 'llm-tool-calling', 'model-selection', 'rag-pipeline-standard', 'structured-output', 'subagents-and-multi-agent', 'system-prompt-engineering', 'tool-design', 'design', 'design-sync', 'dataviz', 'update-config', 'verify', 'debug', 'code-review', 'simplify', 'batch', 'fewer-permission-prompts', 'doctor', 'loop', 'schedule', 'claude-api', 'run', 'run-skill-generator']
[tool_use] Skill {"skill": "llm-tool-calling", "args": "Support bot needs to look up an order and issue a refund over multiple turns — write the tool-calling loop"}
[tool_result] Launching skill: llm-tool-calling
[user] Base directory for this skill: C:\tmp\skills-eval\arm-b\t02-r0\.claude\skills\llm-tool-calling

# LLM Tool Calling Without Frameworks

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

When an LLM needs to invoke a function, pass the tool definitions in the API request payload and turn on strict mode. The provider then constrains the model's output during generation: it cannot return a tool name that wasn't in the payload, cannot omit a required parameter, and cannot produce malformed JSON for the arguments. This is enforcement at the inference layer, and it is the reason you do not need a framework to make tool calling reliable.

Two things follow from this, and both matter:

**Strict mode is opt-in, and the default varies by API.** Tool calling without it is best-effort schema adherence, not a guarantee. OpenAI's own guidance is to always enable strict mode. Set `strict: true` explicitly rather than relying on a default — see "Strict mode defaults" below for why omitting it is dangerous.

**Enforcement covers structure, not content.** The provider constrains the *shape* of the output — types, required fields, enum membership, nesting. It does not reliably constrain *values* — numeric ranges, string lengths, regex patterns. Validate those in your own code.

Write the call directly against the API. The framework abstractions exist because tool calling used to be hard before providers added it natively. It is no longer hard.

## Avoid / Prefer

| Avoid | Prefer |
|---|---|
| Tool calls parsed out of model text | Native tool calling |
| A framework agent abstraction | The provider API directly |
| An omitted `strict` flag | An explicit `strict: true` |
| Value constraints trusted to the schema | Your own check after the call returns |
| A catalog past roughly 20 tools | Dispatchers, or per-request filtering |
| Tool exceptions that raise | Structured errors returned as the tool result |
| A forced tool call on conversational turns | Letting the model decide |

These are defaults, not laws; the rest of this file covers the complexity limits that justify turning `strict` off, and the few cases where a framework is worth its debt.

## Minimal pattern

```text
The model needs to invoke a function
    |
    v
Declare the tool in the request payload with strict: true
    |
    v
Execute it; return errors as data, never as a traceback
    |
    v
Check the stop reason, then validate values the schema cannot enforce
    |
    v
Append the result as a tool-role message and call again
    |
    v
Add a loop, a dispatcher, or a framework only when evals demand it
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## When to use this skill

Apply this skill whenever you encounter any of:

- A user asking to build an "agent," "assistant," "copilot," or any system where an LLM takes actions
- Code that needs an LLM to call a function, query a database, hit an API, or trigger a workflow
- Existing code using `langchain.agents`, `llama_index.agent`, `AgentExecutor`, `create_react_agent`, `initialize_agent`, or similar abstractions — propose rewriting it
- Any time you would otherwise reach for a framework to "orchestrate" LLM tool use
- Code that parses tool calls out of LLM text output via regex, JSON extraction, or prompt-engineered formats — this is a sign someone is reinventing native tool calling badly
- Existing tool definitions without `strict: true` — propose adding it

## Do this: native tool calling with strict mode

```python
import json
from openai import OpenAI

MODEL = "..."   # a pinned, explicit model id — see `model-selection`
client = OpenAI(base_url="...", api_key="...")

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a location.",
            "strict": True,  # opt into constrained decoding
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and country, e.g. 'Cairo, Egypt'",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                # strict mode: every property must be listed in required
                "required": ["location", "unit"],
                # strict mode: required on every object in the schema
                "additionalProperties": False,
            },
        },
    }
]

TOOL_REGISTRY = {
    "get_weather": get_weather,  # your real implementation
}

messages = [{"role": "user", "content": "What's the weather in Cairo?"}]

response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
    tools=tools,
    tool_choice="auto",  # let the model decide; "required" forces a tool call
)

message = response.choices[0].message
messages.append(message)

if message.tool_calls:
    for tool_call in message.tool_calls:
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        try:
            result = TOOL_REGISTRY[name](**args)
        except Exception as e:
            # return errors as data — the model can recover from these
            result = {"error": str(e)}
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result),
        })

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
    )
```

That is the entire tool-calling pattern. Anything more complex is the same loop with more iterations. See `references/agent-loop.md` for the multi-turn version.

If you need to bypass the SDK — for compatibility with non-OpenAI endpoints that the client handles poorly, for zero-dependency code, or to see exactly what goes on the wire — see `references/raw-http.md` for the same example as a raw HTTP POST.

## Strict mode across providers

Both major providers offer the same two capabilities under different parameter names. Check the current docs for your provider; these APIs have moved recently.

| | Strict tool arguments | Structured response |
|---|---|---|
| OpenAI-compatible | `strict: true` on the function definition | `response_format: {"type": "json_schema", ...}` |
| Anthropic | `strict: true` on the tool | `output_config: {"format": {...}}` |

The two are independent and can be combined in one request: strict tools guarantee the arguments the model passes to *your* functions, while structured response guarantees the shape of the model's final answer to *you*. Use strict tools for agentic work; use structured response when you need the model's answer itself parsed. If your task is purely "turn this text into a structured object" and no action is being taken, you want structured response, not a forced tool call.

## Strict mode defaults

If you omit `strict`, what happens depends on which API you are calling, and the difference is easy to miss:

- **Chat Completions** stays non-strict by default. Omitting `strict` means you get best-effort function calling and no guarantee.
- **Responses** attempts to normalize your schema into strict mode automatically, and silently falls back to non-strict if the schema cannot be made compatible. When that fallback happens, the tool in the response comes back showing `strict: false`.

That silent fallback is the trap. You can write a schema you believe is strict, have it quietly rejected for strict mode, and get best-effort behavior with no error. **Set `strict: true` explicitly, and if reliability matters, check what came back in the response rather than assuming.** To deliberately opt out on Responses, set `strict: false` rather than omitting it.

If you send `strict: true` and your schema violates the strict-mode requirements, the request is rejected with details about what is missing — a loud failure, which is what you want.

## Parallel tool calls and strict mode

These two features have a history of interacting badly. Originally they were incompatible: when the model emitted multiple tool calls in one turn, the outputs could violate the supplied schemas, and the guidance was to set `parallel_tool_calls: false`. Parallel calling now works with strict mode on current models, but exceptions remain — fine-tuned models that call multiple functions in one turn have strict mode disabled for those calls, and specific model snapshots have known issues with duplicate parallel calls.

If you need the strict guarantee and you are on a fine-tuned model or an older snapshot, set `parallel_tool_calls: false`. It forces exactly zero or one tool call per turn. Otherwise, verify the behavior on your specific model rather than assuming.

## What the schema actually enforces

The schema is enforced by the provider. The description is a suggestion to the model. But the enforcement has a boundary that is easy to get wrong.

**Reliably enforced (structure):**

- `type` — `string`, `integer`, `number`, `boolean`, `object`, `array`, `null`
- `enum` — the model cannot return a value outside the list
- `required` — required fields are present
- Nested `object` with its own `properties` — structured arguments hold their shape
- `array` with `items` — typed lists
- `anyOf` — union types, including the nullable-field pattern

**Not reliably enforced (content):**

- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`
- `minLength`, `maxLength`
- `minItems`, `maxItems`, `uniqueItems`
- `pattern`, `format`
- `multipleOf`, `minProperties`, `maxProperties`

Support for this second group varies by provider and changes over time. Several SDKs strip these keywords before sending, fold the constraint into the field description, and validate the response against your original schema client-side — so the constraint is checked *after* generation rather than enforced *during* it. Some providers have since added native support for parts of this list.

**The rule:** put structural constraints in the schema and rely on them. Put value constraints in the schema too — they cost nothing and may be honored — but validate them in your own code and do not assume the model was constrained by them. If a value constraint is critical to correctness, check it after the tool call returns.

## Strict mode requirements

Turning on `strict: true` imposes schema requirements that will reject your request if you get them wrong:

**Every object needs `additionalProperties: false`.** Not just the root — every nested object in the schema.

**Every property must appear in `required`.** You cannot express an optional field by omitting it from `required`. Instead, make the type nullable:

```python
"notes": {
    "anyOf": [
        {"type": "string"},
        {"type": "null"},
    ]
}
```

The model can now return `null`, and your code handles the absence explicitly.

**Nesting is capped.** OpenAI-compatible endpoints cap schema nesting at five levels. Flatten deeply nested structures.

**Complexity limits apply.** Anthropic enforces limits on strict tools per request, on total optional parameters across all strict schemas, and on parameters using union types — union types are the expensive ones, because they multiply out during grammar compilation. Exceeding these returns a 400. If you hit the limit, reserve `strict: true` for the tools where a schema violation would actually cause damage, make parameters required where you can, and flatten nested structures.

**First call with a new schema is slower.** Strict mode compiles your schema into a grammar. That compilation is cached (Anthropic caches for 24 hours from last use), so only the first request with a given schema pays the cost. Changing the schema, or changing the set of tools in the request, invalidates the cache.

## Don't do this

Three patterns to recognize and replace:

**Prompt-engineered tool calling.** If the code has a system prompt that says "Respond with a JSON object of the form `{tool: ..., args: ...}`" and parses the response, replace it with native tool calling. The prompt-engineered version fails on a measurable fraction of calls. Native tool calling with strict mode does not fail this way.

**Framework agent abstractions.** `AgentExecutor`, `initialize_agent`, `create_react_agent`, and similar constructions wrap the same native primitives you have direct access to, while adding: a fixed loop you cannot easily modify, error handling that converts tool failures into prompt text rather than surfacing them (turning a debuggable exception into a silent retry), telemetry that is hard to integrate with existing observability, and an upgrade treadmill where the framework's API changes faster than the provider's. Framework wrappers also frequently expose their own `strict` flag with its own default, adding a second place where the guarantee can be silently off. See `references/why-not-frameworks.md`.

**ReAct-style text parsing.** Prompts that ask the model to output `Thought: ... Action: ... Observation: ...` and parse them with regex are pre-native-tool-calling. There is no reason to use this today unless your model genuinely lacks tool support, in which case pick a different model.

## Common pitfalls

**Leaving strict mode off.** Plain tool calling is best-effort. If you have not set `strict: true`, you do not have the guarantee, and code that assumes you do will break intermittently and confusingly. Turn it on unless you have hit a complexity limit.

**Assuming strict mode covers value constraints.** It covers structure. A `pattern` on an ID field or a `maximum` on a count may be stripped before the request is even sent. Validate values yourself.

**Assuming strict mode is absolute.** Two cases break conformance even with strict on: a refusal (the model declines for safety reasons and the refusal message takes precedence over the schema) and hitting the token limit mid-generation (the output is truncated and therefore incomplete). Check `stop_reason` / `finish_reason` before parsing, and handle both.

**Relying on enum capitalization.** Structured outputs do not guarantee the casing of enum and const values — a value may come back differing from your schema only in capitalization. Compare enum values case-insensitively, and avoid enums whose members differ only in case.

**Forgetting to send tool results back.** After executing the tool, append a message with `role: "tool"` and `tool_call_id` matching the original call, then call the API again. Skipping this leaves a dangling tool call with no observation and the next response will be incoherent.

**Sending tool results as a user message.** The result goes in a message with `role: "tool"`, not `role: "user"`. Using `user` works on some providers and fails on others.

**Letting tool execution errors raise.** Catch the exception and return a structured error as the tool result. The model can recover from "the tool returned an error" but not from a traceback that killed your process.

**Overusing `tool_choice="required"`.** Forcing a tool call makes sense when the entire purpose of the call is to invoke something. For conversational interfaces, leave it on `"auto"`; forcing it makes the assistant call tools on chitchat turns.

**Forgetting that tool descriptions are prompts.** The `description` field on each tool and each parameter is fed to the model. Vague descriptions cause misuse. Write them as if briefing a junior engineer: what the tool does, when to use it, when not to, and what each parameter means.

**Writing schemas that don't constrain anything.** The provider can only enforce what you tell it. `{"type": "string"}` accepts any string. `{"type": "object"}` with no `properties` accepts any shape. If the value is genuinely constrained to a fixed set, use `enum` — that one *is* enforced.

**Defining too many tools.** The practical safe zone is roughly 10-20 tools in a single reasoning context. Above that, selection accuracy degrades — and the degradation is a cliff, not a slope. Berkeley Function Calling Leaderboard data has shown accuracy collapsing from around 43% to 2% on scheduling tasks as the catalog grew from 4 tools to 51. The failure mode is not graceful: the model hallucinates a tool name or calls the right tool with arguments borrowed from a different tool's schema. API-level caps (OpenAI allows up to 128 tools) are far above where real degradation begins. Group tools under dispatchers, split across specialized assistants, or filter the tool list per request by relevance. See `references/many-tools.md`.

**Putting sensitive data in tool schemas.** Schemas are processed and cached separately from message content and do not carry the same data-handling guarantees — OpenAI states that JSON Schemas supplied with structured outputs are not Zero Data Retention eligible, and Anthropic caches compiled schema grammars for 24 hours. Keep regulated or secret data out of tool names, parameter names, descriptions, enum values, and patterns. It belongs in the message content.

## When to break the rules

A framework wrapper is justified in a small number of cases:

- You are prototyping and intend to throw the code away within days.
- You need a specific framework feature (for example, LangGraph's checkpointing) and have evaluated that building it yourself costs more than the framework debt.
- The framework is already deeply integrated and removing it costs more than keeping it.

Turning `strict: true` off is justified when:

- You have hit a complexity limit and this particular tool's schema violations are harmless.
- You need a JSON Schema feature that strict mode rejects, and the structural guarantee matters less than the expressiveness.

Outside these cases, write the call directly and turn strict mode on.

## Success criteria

Native tool calling and strict mode are claims about reliability, so they should show up as numbers:

- **Tool-selection correctness**, including the should-not-call direction — the suite for this is `evals-before-shipping/references/tool-call-suite.md`
- **Argument correctness**: the rate of missing, malformed, or wrong-schema arguments, which strict mode should drive to zero for structural errors
- **Hallucinated tool names**, which under strict mode is a bug rather than a rate
- **Value-constraint violations caught by your own validation** — a non-zero count is the evidence that the schema was never enforcing them
- **Unhandled refusals and truncations**: runs that crashed or silently parsed a partial payload instead of checking the stop reason
- **Tool calls per completed task**, which is where an oversized catalog and a vague description show up before anything else fails
- **Tool-result tokens per task**, since oversized payloads are paid for on every subsequent turn

If none of these move after you switch off a prompt-parsed or framework-wrapped implementation, the rewrite did not help on that task and the old code was not your problem.

## References

- `references/openai-format.md` — exact payload shape for OpenAI-compatible APIs, including how tools, strict, and tool_choice interact
- `references/raw-http.md` — the same example as a raw HTTP POST, for cases where the SDK is not the right fit
- `references/anthropic-format.md` — Anthropic's tool-use format, `output_config`, and the differences from OpenAI's
- `references/agent-loop.md` — the multi-turn loop, including stopping conditions and max-iteration handling
- `references/many-tools.md` — patterns for systems with more than ~15 tools, and working within strict-mode complexity limits
- `references/why-not-frameworks.md` — specific failure modes in `AgentExecutor` and similar abstractions, with code-level examples

ARGUMENTS: Support bot needs to look up an order and issue a refund over multiple turns — write the tool-calling loop
[tool_use] Read {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t02-r0\\.claude\\skills\\llm-tool-calling\\references\\agent-loop.md"}
[tool_result] 1	# The Multi-Turn Tool Loop
2	
3	> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.
4	
5	The single-turn example in the skill is the loop with `max_iterations=1`. This is the general form. It is about forty lines, and no framework does anything meaningfully different.
6	
7	This file covers the *mechanics*. For whether you should be running a loop at all rather than a fixed pipeline, see `agent-vs-workflow-decision`.
8	
9	## The loop
10	
11	```python
12	import json
13	from dataclasses import dataclass, field
14	
15	MAX_ITERATIONS = 10
16	
17	@dataclass
18	class RunResult:
19	    text: str | None
20	    stop: str                      # "done" | "max_iterations" | "budget" | "refusal"
21	    iterations: int
22	    tool_calls: list = field(default_factory=list)
23	    usage: dict = field(default_factory=dict)
24	
25	def run(user_message: str, tools, registry, max_iterations=MAX_ITERATIONS) -> RunResult:
26	    messages = [{"role": "user", "content": user_message}]
27	    calls, usage = [], {"in": 0, "out": 0}
28	
29	    for i in range(1, max_iterations + 1):
30	        response = client.chat.completions.create(
31	            model=MODEL, messages=messages, tools=tools, tool_choice="auto",
32	        )
33	        usage["in"] += response.usage.prompt_tokens
34	        usage["out"] += response.usage.completion_tokens
35	
36	        choice = response.choices[0]
37	        messages.append(choice.message)          # verbatim, before anything else
38	
39	        if choice.finish_reason == "length":
40	            raise RuntimeError(f"truncated on iteration {i}; raise max_completion_tokens")
41	
42	        if not choice.message.tool_calls:
43	            return RunResult(choice.message.content, "done", i, calls, usage)
44	
45	        for tc in choice.message.tool_calls:
46	            calls.append(tc.function.name)
47	            messages.append({
48	                "role": "tool",
49	                "tool_call_id": tc.id,
50	                "content": json.dumps(execute(tc, registry)),
51	            })
52	
53	    return RunResult(None, "max_iterations", max_iterations, calls, usage)
54	
55	
56	def execute(tool_call, registry) -> dict:
57	    name = tool_call.function.name
58	    if name not in registry:
59	        # the model invented a tool; tell it so rather than raising
60	        return {"error": f"No tool named {name!r}. Available: {sorted(registry)}"}
61	    try:
62	        args = json.loads(tool_call.function.arguments)
63	    except json.JSONDecodeError as e:
64	        return {"error": f"Arguments were not valid JSON: {e}"}
65	    try:
66	        return {"result": registry[name](**args)}
67	    except Exception as e:
68	        return {"error": f"{type(e).__name__}: {e}"}
69	```
70	
71	Everything important is in the small decisions:
72	
73	**Append the assistant message before executing anything.** If a tool raises and you unwind, the transcript still has to be coherent for the retry.
74	
75	**Hitting the iteration cap is a return value, not an exception.** The caller decides whether a partial run is useful. Raising there loses the transcript, the token count, and the tool history — the three things you need to debug it.
76	
77	**Tool errors are data.** Unknown tool name, unparseable arguments, and a raised exception all become tool results the model can read and react to. The only thing that should escape the loop is a failure the model cannot possibly recover from.
78	
79	**Track usage as you go.** Per-run token cost is the number you need for `model-selection` and for any budget cap, and you cannot reconstruct it afterward.
80	
81	## Stopping conditions
82	
83	An iteration cap alone is the minimum, and it is not enough for anything unattended. Four conditions, in the order they tend to matter:
84	
85	```python
86	class Stop(Exception): ...
87	
88	def check(state):
89	    if state.iterations >= MAX_ITERATIONS:
90	        raise Stop("max_iterations")
91	    if state.cost_usd >= MAX_COST_USD:
92	        raise Stop("budget")
93	    if state.elapsed_s >= MAX_WALL_CLOCK_S:
94	        raise Stop("timeout")
95	    if state.repeated_identical_calls >= 3:
96	        raise Stop("stuck")
97	```
98	
99	The last one catches the most common real failure: the model calls the same tool with the same arguments, gets the same result, and does it again. Hash `(name, arguments)` per iteration and count repeats.
100	
101	```python
102	signature = (tc.function.name, tc.function.arguments)
103	state.seen[signature] += 1
104	if state.seen[signature] >= 3:
105	    # break the cycle in-band before you kill the run
106	    result = {"error": "You have already called this tool with these exact arguments "
107	                       "twice and received the same result. Try different arguments "
108	                       "or answer with what you have."}
109	```
110	
111	Telling the model it is looping frequently unsticks it. Do that first; kill the run only if it doesn't work.
112	
113	## Where to put the budget cap
114	
115	Cost, not iterations, is what actually hurts. Iterations are a poor proxy — one call with 80K tokens of context costs more than six small ones.
116	
117	```python
118	cost = (usage["in"] / 1e6) * PRICE_IN + (usage["out"] / 1e6) * PRICE_OUT
119	```
120	
121	Check it *after* each response and *before* the next request. A cap checked only at the top of the loop lets one expensive iteration blow through it.
122	
123	For a per-run ceiling the model itself can pace against, Anthropic's task budgets pass a token allowance in `output_config.task_budget` and inject a countdown the model can see, so it winds down gracefully instead of being cut off. That is a different mechanism from `max_tokens`, which is an enforced per-response cap the model knows nothing about.
124	
125	## Context growth
126	
127	Every iteration re-sends the whole transcript. A ten-iteration run with large tool results can spend most of its budget re-reading its own history.
128	
129	Three mitigations, cheapest first:
130	
131	1. **Return less.** A tool that returns 200 rows when the model needs 5 is the actual bug. See `tool-design`.
132	2. **Truncate old tool results in place** — keep the last N verbatim, replace older ones with a one-line summary. Note that this invalidates the prompt cache from the edit point onward, so truncate in batches rather than every turn.
133	3. **Clear or compact server-side.** Anthropic's context editing clears old tool results (`clear_tool_uses_20250919`) and thinking blocks; compaction summarizes instead. Both are provider features that spare you writing this logic.
134	
135	See `context-and-memory` for the full treatment.
136	
137	## Streaming a loop
138	
139	Streaming inside a tool loop only helps the final turn — the intermediate turns end in tool calls nobody is reading. A reasonable pattern: run intermediate iterations non-streaming, and stream only once the model returns no tool calls. If you want live progress in the meantime, emit your own events as each tool starts and finishes; that is more legible to a user than raw token deltas anyway.
140	
141	## What not to add
142	
143	**A planning step that plans and then ignores the plan.** If you want a plan, make the plan a tool call whose output is in the transcript, so deviation is visible.
144	
145	**A reflection pass on every iteration.** It doubles cost. Add it after measuring that the loop actually fails in a way reflection fixes.
146	
147	**A framework, for this.** The whole mechanism is above. What you would be buying is a fixed control flow, error handling that converts exceptions into prompt text, and an upgrade treadmill. See `why-not-frameworks.md`.
148	
[tool_use] Read {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t02-r0\\.claude\\skills\\llm-tool-calling\\references\\anthropic-format.md"}
[tool_result] 1	# Anthropic Tool Use Format
2	
3	> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.
4	
5	Same two capabilities as the OpenAI-compatible side — constrained tool arguments and a constrained final answer — with a different request shape and a content-block response model.
6	
7	## Tool definition
8	
9	```python
10	tools = [{
11	    "name": "get_weather",                  # ^[a-zA-Z0-9_-]{1,128}$
12	    "description": (
13	        "Get the current weather for a location. Returns temperature in the "
14	        "requested unit, conditions, and humidity. Use for current conditions "
15	        "only — this tool does not return forecasts."
16	    ),
17	    "strict": True,                         # top-level, beside name/description
18	    "input_schema": {                       # not "parameters"
19	        "type": "object",
20	        "properties": {
21	            "location": {"type": "string", "description": "City and country"},
22	            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
23	        },
24	        "required": ["location"],
25	        "additionalProperties": False,
26	    },
27	    "input_examples": [                     # optional; see tool-design
28	        {"location": "Cairo, Egypt", "unit": "celsius"},
29	        {"location": "New York, NY"},
30	    ],
31	}]
32	```
33	
34	Four differences from the OpenAI shape, all of which are silent failures if you get them wrong:
35	
36	| | OpenAI-compatible | Anthropic |
37	|---|---|---|
38	| Wrapper | `{"type": "function", "function": {...}}` | flat object |
39	| Schema key | `parameters` | `input_schema` |
40	| `strict` lives | inside `function` | top level of the tool |
41	| `max_tokens` | optional | **required on every request** |
42	
43	Anthropic's docs ask for more description than most people write — aim for 3–4 sentences, covering what the tool does, when *not* to use it, what each parameter means, and what it does not return.
44	
45	## The request
46	
47	```python
48	import anthropic
49	
50	client = anthropic.Anthropic()
51	
52	response = client.messages.create(
53	    model=MODEL,
54	    max_tokens=4096,
55	    tools=tools,
56	    messages=[{"role": "user", "content": "What's the weather in Cairo?"}],
57	)
58	```
59	
60	`tool_choice` takes `{"type": "auto"}` (default with tools), `{"type": "any"}` (must call something), `{"type": "tool", "name": "..."}` (must call that one), or `{"type": "none"}`.
61	
62	Two restrictions worth knowing before you depend on forced tool use: manual extended thinking (`thinking: {type: "enabled"}`) rejects `any` and `tool`, and the Fable/Mythos 5.1 tier returns a 400 for both. The replacement is `auto` plus an instruction naming the tool, with `strict: true` keeping the arguments valid — or structured outputs, if the forced call only ever existed to get JSON back.
63	
64	Changing `tool_choice` mid-conversation invalidates cached *message* blocks. Tool definitions and the system prompt stay cached.
65	
66	## The response is content blocks
67	
68	```python
69	{
70	  "role": "assistant",
71	  "stop_reason": "tool_use",
72	  "content": [
73	    {"type": "text", "text": "I'll check the current conditions in Cairo."},
74	    {"type": "tool_use", "id": "toolu_01A...", "name": "get_weather",
75	     "input": {"location": "Cairo, Egypt", "unit": "celsius"}}
76	  ]
77	}
78	```
79	
80	`input` is an **already-parsed object**, not a JSON string — no `json.loads()` on the way in. Text and `tool_use` blocks coexist; iterate the list and match on `type` rather than assuming positions.
81	
82	`stop_reason` is the loop control:
83	
84	| Value | Meaning |
85	|---|---|
86	| `tool_use` | Run the tools, send results, call again |
87	| `end_turn` | Done |
88	| `max_tokens` | Truncated — raise the cap and retry |
89	| `refusal` | Declined by a safety classifier; HTTP 200, and you are billed. Check before reading `content` |
90	| `pause_turn` | A long-running server tool paused; resume by passing the response back |
91	
92	## Returning results
93	
94	Results are `tool_result` blocks inside a **user** message, all of them in one message:
95	
96	```python
97	messages.append({"role": "assistant", "content": response.content})   # verbatim
98	
99	results = []
100	for block in response.content:
101	    if block.type == "tool_use":
102	        try:
103	            output = TOOL_REGISTRY[block.name](**block.input)
104	            results.append({
105	                "type": "tool_result",
106	                "tool_use_id": block.id,
107	                "content": json.dumps(output),
108	            })
109	        except Exception as e:
110	            results.append({
111	                "type": "tool_result",
112	                "tool_use_id": block.id,
113	                "content": f"Error: {e}. Retry with a narrower date range.",
114	                "is_error": True,
115	            })
116	
117	messages.append({"role": "user", "content": results})
118	```
119	
120	**Splitting parallel results across several user messages silently teaches the model to stop making parallel calls.** One message, every result, including the failures — a dropped `tool_result` is a protocol error, not a way to hide an error.
121	
122	Errors go back as `is_error: True` with text the agent can act on. "Retry with a narrower range" recovers; a stack trace does not.
123	
124	## Structured final answers
125	
126	Independent of tools. Constrains the model's answer to *you*:
127	
128	```python
129	response = client.messages.create(
130	    model=MODEL,
131	    max_tokens=4096,
132	    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
133	    messages=[...],
134	)
135	```
136	
137	The Python SDK offers `client.messages.parse()` with a Pydantic model, returning `response.parsed_output`. The older top-level `output_format` parameter is superseded by `output_config.format`.
138	
139	Combining strict tools with a structured response in one request is supported and documented: strict tools guarantee the arguments your functions receive; the output config guarantees the shape of the final answer. See `structured-output` for when each is the right tool.
140	
141	Changing `output_config.format` invalidates the prompt cache for that thread. Changing only a tool's `name` or `description` does not.
142	
143	## Strict-mode limits and caching
144	
145	- Schemas compile to grammars, and compiled grammars are cached for up to **24 hours since last use**. Only the first request with a given schema pays compilation latency.
146	- Changing a schema, or changing the set of tools in the request, recompiles.
147	- Anthropic enforces complexity limits on a request: how many strict tools, how many optional parameters in total, and how many union-typed parameters. Unions are the expensive ones — they multiply out during compilation. Exceeding a limit returns a 400, so you find out immediately.
148	- **Keep regulated data out of schemas.** Compiled schemas are cached separately from message content and do not carry the same protections. Anthropic's guidance is explicit that PHI must not appear in property names, enum values, const values, or pattern regexes. It belongs in message content.
149	
150	If you hit a complexity limit: reserve `strict: true` for the tools where a violation would actually do damage, make parameters required rather than optional where you can, and flatten nested structures.
151	
152	## Prompt caching for tool definitions
153	
154	Render order is `tools` → `system` → `messages`. Tool definitions sit at the very front of the prefix, so they are the cheapest thing to cache and the most expensive thing to churn.
155	
156	```python
157	tools = [
158	    *STABLE_TOOLS,
159	    {**LAST_TOOL, "cache_control": {"type": "ephemeral"}},   # breakpoint after the tool block
160	]
161	```
162	
163	Serialize the tool list deterministically — same order, same key order, every request. A dict that iterates differently between processes will quietly cost you the cache on half your traffic. Verify with `usage.cache_read_input_tokens`: a persistent zero means something in the prefix is moving.
164	
[assistant] Here's the multi-turn tool loop for the support bot, using Anthropic's Messages API. Two tools — `lookup_order` and `issue_refund` — with strict schemas, and a loop that keeps feeding tool results back until the model gives a final answer.
[tool_use] Write {"file_path": "C:\\tmp\\skills-eval\\arm-b\\t02-r0\\support_bot.py", "content": "\"\"\"\nSupport bot: looks up an order and issues a refund, over multiple turns.\n\nTwo tools, native Anthropic tool calling with strict mode. The loop below\nappends every assistant turn and every tool result verbatim, checks\nstop_reason before doing anything else, and returns tool errors as data\nso the model can react to them instead of crashing the process.\n\"\"\"\n\nimport json\nfrom dataclasses import dataclass, field\n\nimport anthropic\n\nMODEL = \"claude-sonnet-5\"\nMAX_ITERATIONS = 10\n\nclient = anthropic.Anthropic()\n\n# --- Mock backend -----------------------------------------------------\n# Replace with real calls to your order-management / payment systems.\n\n_ORDERS = {\n    \"ORD-1001\": {\n        \"order_id\": \"ORD-1001\",\n        \"status\": \"delivered\",\n        \"total_usd\": 49.99,\n        \"refunded_usd\": 0.0,\n        \"items\": [\"Wireless Mouse\"],\n    },\n    \"ORD-1002\": {\n        \"order_id\": \"ORD-1002\",\n        \"status\": \"delivered\",\n        \"total_usd\": 129.00,\n        \"refunded_usd\": 129.00,\n        \"items\": [\"Mechanical Keyboard\"],\n    },\n}\n\n\ndef lookup_order(order_id: str) -> dict:\n    order = _ORDERS.get(order_id)\n    if order is None:\n        return {\"error\": f\"No order found with id {order_id!r}.\"}\n    return order\n\n\ndef issue_refund(order_id: str, amount_usd: float, reason: str) -> dict:\n    order = _ORDERS.get(order_id)\n    if order is None:\n        return {\"error\": f\"No order found with id {order_id!r}.\"}\n\n    already_refunded = order[\"refunded_usd\"]\n    remaining = round(order[\"total_usd\"] - already_refunded, 2)\n\n    # Value constraints the schema can't enforce — checked here, not trusted\n    # to `minimum`/`maximum` in the JSON Schema.\n    if amount_usd <= 0:\n        return {\"error\": \"amount_usd must be greater than 0.\"}\n    if amount_usd > remaining:\n        return {\n            \"error\": (\n                f\"Refund of {amount_usd} exceeds remaining refundable amount \"\n                f\"({remaining}) for {order_id}.\"\n            )\n        }\n\n    order[\"refunded_usd\"] = round(already_refunded + amount_usd, 2)\n    return {\n        \"order_id\": order_id,\n        \"refunded_usd\": amount_usd,\n        \"remaining_refundable_usd\": round(remaining - amount_usd, 2),\n        \"reason\": reason,\n        \"confirmation_id\": f\"RF-{order_id}-{int(order['refunded_usd'] * 100)}\",\n    }\n\n\nTOOL_REGISTRY = {\n    \"lookup_order\": lookup_order,\n    \"issue_refund\": issue_refund,\n}\n\nTOOLS = [\n    {\n        \"name\": \"lookup_order\",\n        \"description\": (\n            \"Look up an order by its order ID. Returns the order status, total \"\n            \"amount charged in USD, amount already refunded, and the items in the \"\n            \"order. Use this before issuing a refund to confirm the order exists \"\n            \"and check how much is still refundable. Does not modify anything.\"\n        ),\n        \"strict\": True,\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"order_id\": {\n                    \"type\": \"string\",\n                    \"description\": \"The order identifier, e.g. 'ORD-1001'.\",\n                },\n            },\n            \"required\": [\"order_id\"],\n            \"additionalProperties\": False,\n        },\n    },\n    {\n        \"name\": \"issue_refund\",\n        \"description\": (\n            \"Issue a refund against an order. This charges money back to the \"\n            \"customer and cannot be undone — only call it after confirming the \"\n            \"order ID and refund amount with lookup_order, and after the customer \"\n            \"has clearly asked for a refund. Fails if the amount exceeds what is \"\n            \"still refundable on the order.\"\n        ),\n        \"strict\": True,\n        \"input_schema\": {\n            \"type\": \"object\",\n            \"properties\": {\n                \"order_id\": {\n                    \"type\": \"string\",\n                    \"description\": \"The order identifier to refund, e.g. 'ORD-1001'.\",\n                },\n                \"amount_usd\": {\n                    \"type\": \"number\",\n                    \"description\": \"Refund amount in USD. Must not exceed the order's remaining refundable balance.\",\n                },\n                \"reason\": {\n                    \"type\": \"string\",\n                    \"description\": \"Short reason for the refund, shown to the customer and kept for records.\",\n                },\n            },\n            \"required\": [\"order_id\", \"amount_usd\", \"reason\"],\n            \"additionalProperties\": False,\n        },\n    },\n]\n\nSYSTEM_PROMPT = (\n    \"You are a support assistant. You can look up orders and issue refunds. \"\n    \"Always look up the order before refunding it, confirm the refund amount \"\n    \"and reason make sense given the order, and only issue a refund the \"\n    \"customer has actually asked for. If a tool returns an error, explain it \"\n    \"to the customer in plain language rather than retrying blindly.\"\n)\n\n\n@dataclass\nclass RunResult:\n    text: str | None\n    stop: str  # \"done\" | \"max_iterations\" | \"refusal\" | \"error\"\n    iterations: int\n    tool_calls: list = field(default_factory=list)\n    usage: dict = field(default_factory=lambda: {\"in\": 0, \"out\": 0})\n\n\ndef execute_tool(block) -> dict:\n    name = block.name\n    if name not in TOOL_REGISTRY:\n        return {\"error\": f\"No tool named {name!r}. Available: {sorted(TOOL_REGISTRY)}\"}\n    try:\n        return TOOL_REGISTRY[name](**block.input)\n    except Exception as e:\n        return {\"error\": f\"{type(e).__name__}: {e}\"}\n\n\ndef run(messages: list, max_iterations: int = MAX_ITERATIONS) -> RunResult:\n    \"\"\"Drive the conversation until the model stops calling tools.\n\n    `messages` is mutated in place so the caller can keep it across\n    invocations (e.g. one call per incoming customer message).\n    \"\"\"\n    calls = []\n    usage = {\"in\": 0, \"out\": 0}\n    seen_calls: dict[tuple, int] = {}\n\n    for i in range(1, max_iterations + 1):\n        response = client.messages.create(\n            model=MODEL,\n            max_tokens=1024,\n            system=SYSTEM_PROMPT,\n            tools=TOOLS,\n            messages=messages,\n        )\n        usage[\"in\"] += response.usage.input_tokens\n        usage[\"out\"] += response.usage.output_tokens\n\n        if response.stop_reason == \"refusal\":\n            return RunResult(None, \"refusal\", i, calls, usage)\n        if response.stop_reason == \"max_tokens\":\n            raise RuntimeError(f\"truncated on iteration {i}; raise max_tokens\")\n\n        messages.append({\"role\": \"assistant\", \"content\": response.content})  # verbatim\n\n        if response.stop_reason != \"tool_use\":\n            text = \"\".join(b.text for b in response.content if b.type == \"text\")\n            return RunResult(text, \"done\", i, calls, usage)\n\n        results = []\n        for block in response.content:\n            if block.type != \"tool_use\":\n                continue\n\n            signature = (block.name, json.dumps(block.input, sort_keys=True))\n            seen_calls[signature] = seen_calls.get(signature, 0) + 1\n            calls.append(block.name)\n\n            if seen_calls[signature] >= 3:\n                output = {\n                    \"error\": (\n                        \"You've called this tool with these exact arguments \"\n                        \"multiple times and gotten the same result. Try different \"\n                        \"arguments, ask the customer for clarification, or answer \"\n                        \"with what you have.\"\n                    )\n                }\n            else:\n                output = execute_tool(block)\n\n            results.append({\n                \"type\": \"tool_result\",\n                \"tool_use_id\": block.id,\n                \"content\": json.dumps(output),\n                **({\"is_error\": True} if \"error\" in output else {}),\n            })\n\n        messages.append({\"role\": \"user\", \"content\": results})  # all results, one message\n\n    return RunResult(None, \"max_iterations\", max_iterations, calls, usage)\n\n\nif __name__ == \"__main__\":\n    conversation = []\n    print(\"Support bot ready. Type 'quit' to exit.\")\n    while True:\n        user_input = input(\"\\ncustomer> \").strip()\n        if user_input.lower() in {\"quit\", \"exit\"}:\n            break\n\n        conversation.append({\"role\": \"user\", \"content\": user_input})\n        result = run(conversation)\n\n        if result.stop == \"refusal\":\n            print(\"bot> I'm not able to help with that request.\")\n        elif result.stop == \"max_iterations\":\n            print(\"bot> (took too many steps — escalating to a human agent.)\")\n        else:\n            print(f\"bot> {result.text}\")\n"}
[tool_result] File created successfully at: C:\tmp\skills-eval\arm-b\t02-r0\support_bot.py (file state is current in your context — no need to Read it back)
[assistant] I wrote this to `support_bot.py`. Key points on how it works:

- **Two strict tools**: `lookup_order` (read-only) and `issue_refund` (side-effecting — its description explicitly tells the model to look up the order first and only refund on a clear customer request).
- **The loop** (`run`): each iteration calls the API, appends the assistant turn verbatim, then checks `stop_reason` — `tool_use` executes tools and loops again, anything else returns the final text. `refusal` and `max_tokens` are checked explicitly rather than assumed away.
- **Value validation lives in `issue_refund` itself** (amount > 0, amount ≤ remaining refundable) since JSON Schema `minimum`/`maximum` aren't reliably enforced by strict mode — the tool is the actual guardrail.
- **Tool errors return as data** (`{"error": ...}` + `is_error: True`) instead of raising, so the model can explain the problem to the customer instead of the process crashing.
- **Repeated-call guard**: if the model calls the same tool with identical arguments 3 times, it gets told so in-band instead of looping forever.
- `conversation` is a plain list the caller keeps across turns, so `run()` can be called once per incoming customer message in a real chat loop.

Note: this uses mock in-memory order data (`_ORDERS`) — swap `lookup_order`/`issue_refund` for real calls to your order and payment systems. Since `issue_refund` moves real money, you may also want a human-confirmation step before it executes in production (not added here since you didn't ask for it — flag if you want that gate).