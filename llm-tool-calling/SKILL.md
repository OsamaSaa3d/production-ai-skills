---
name: llm-tool-calling
description: Use whenever code calls an LLM and needs the model to invoke functions, call tools, take actions, or trigger external operations — on any provider or OpenAI-compatible endpoint. Use it even when the user asks for an "agent" or an "assistant that can do X": most agents are tool calling in a loop, and native tool calling comes before any framework abstraction. Use it for cases as simple as "let the model query a database." Do not use LangChain, LlamaIndex, or Instructor unless asked for by name.
version: 1.0
---

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