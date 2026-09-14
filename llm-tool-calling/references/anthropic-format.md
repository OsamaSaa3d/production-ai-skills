# Anthropic Tool Use Format

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Same two capabilities as the OpenAI-compatible side — constrained tool arguments and a constrained final answer — with a different request shape and a content-block response model.

## Tool definition

```python
tools = [{
    "name": "get_weather",                  # ^[a-zA-Z0-9_-]{1,128}$
    "description": (
        "Get the current weather for a location. Returns temperature in the "
        "requested unit, conditions, and humidity. Use for current conditions "
        "only — this tool does not return forecasts."
    ),
    "strict": True,                         # top-level, beside name/description
    "input_schema": {                       # not "parameters"
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City and country"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["location"],
        "additionalProperties": False,
    },
    "input_examples": [                     # optional; see tool-design
        {"location": "Cairo, Egypt", "unit": "celsius"},
        {"location": "New York, NY"},
    ],
}]
```

Four differences from the OpenAI shape, all of which are silent failures if you get them wrong:

| | OpenAI-compatible | Anthropic |
|---|---|---|
| Wrapper | `{"type": "function", "function": {...}}` | flat object |
| Schema key | `parameters` | `input_schema` |
| `strict` lives | inside `function` | top level of the tool |
| `max_tokens` | optional | **required on every request** |

Anthropic's docs ask for more description than most people write — aim for 3–4 sentences, covering what the tool does, when *not* to use it, what each parameter means, and what it does not return.

## The request

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model=MODEL,
    max_tokens=4096,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in Cairo?"}],
)
```

`tool_choice` takes `{"type": "auto"}` (default with tools), `{"type": "any"}` (must call something), `{"type": "tool", "name": "..."}` (must call that one), or `{"type": "none"}`.

Two restrictions worth knowing before you depend on forced tool use: manual extended thinking (`thinking: {type: "enabled"}`) rejects `any` and `tool`, and the Fable/Mythos 5.1 tier returns a 400 for both. The replacement is `auto` plus an instruction naming the tool, with `strict: true` keeping the arguments valid — or structured outputs, if the forced call only ever existed to get JSON back.

Changing `tool_choice` mid-conversation invalidates cached *message* blocks. Tool definitions and the system prompt stay cached.

## The response is content blocks

```python
{
  "role": "assistant",
  "stop_reason": "tool_use",
  "content": [
    {"type": "text", "text": "I'll check the current conditions in Cairo."},
    {"type": "tool_use", "id": "toolu_01A...", "name": "get_weather",
     "input": {"location": "Cairo, Egypt", "unit": "celsius"}}
  ]
}
```

`input` is an **already-parsed object**, not a JSON string — no `json.loads()` on the way in. Text and `tool_use` blocks coexist; iterate the list and match on `type` rather than assuming positions.

`stop_reason` is the loop control:

| Value | Meaning |
|---|---|
| `tool_use` | Run the tools, send results, call again |
| `end_turn` | Done |
| `max_tokens` | Truncated — raise the cap and retry |
| `refusal` | Declined by a safety classifier; HTTP 200, and you are billed. Check before reading `content` |
| `pause_turn` | A long-running server tool paused; resume by passing the response back |

## Returning results

Results are `tool_result` blocks inside a **user** message, all of them in one message:

```python
messages.append({"role": "assistant", "content": response.content})   # verbatim

results = []
for block in response.content:
    if block.type == "tool_use":
        try:
            output = TOOL_REGISTRY[block.name](**block.input)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(output),
            })
        except Exception as e:
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": f"Error: {e}. Retry with a narrower date range.",
                "is_error": True,
            })

messages.append({"role": "user", "content": results})
```

**Splitting parallel results across several user messages silently teaches the model to stop making parallel calls.** One message, every result, including the failures — a dropped `tool_result` is a protocol error, not a way to hide an error.

Errors go back as `is_error: True` with text the agent can act on. "Retry with a narrower range" recovers; a stack trace does not.

## Structured final answers

Independent of tools. Constrains the model's answer to *you*:

```python
response = client.messages.create(
    model=MODEL,
    max_tokens=4096,
    output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    messages=[...],
)
```

The Python SDK offers `client.messages.parse()` with a Pydantic model, returning `response.parsed_output`. The older top-level `output_format` parameter is superseded by `output_config.format`.

Combining strict tools with a structured response in one request is supported and documented: strict tools guarantee the arguments your functions receive; the output config guarantees the shape of the final answer. See `structured-output` for when each is the right tool.

Changing `output_config.format` invalidates the prompt cache for that thread. Changing only a tool's `name` or `description` does not.

## Strict-mode limits and caching

- Schemas compile to grammars, and compiled grammars are cached for up to **24 hours since last use**. Only the first request with a given schema pays compilation latency.
- Changing a schema, or changing the set of tools in the request, recompiles.
- Anthropic enforces complexity limits on a request: how many strict tools, how many optional parameters in total, and how many union-typed parameters. Unions are the expensive ones — they multiply out during compilation. Exceeding a limit returns a 400, so you find out immediately.
- **Keep regulated data out of schemas.** Compiled schemas are cached separately from message content and do not carry the same protections. Anthropic's guidance is explicit that PHI must not appear in property names, enum values, const values, or pattern regexes. It belongs in message content.

If you hit a complexity limit: reserve `strict: true` for the tools where a violation would actually do damage, make parameters required rather than optional where you can, and flatten nested structures.

## Prompt caching for tool definitions

Render order is `tools` → `system` → `messages`. Tool definitions sit at the very front of the prefix, so they are the cheapest thing to cache and the most expensive thing to churn.

```python
tools = [
    *STABLE_TOOLS,
    {**LAST_TOOL, "cache_control": {"type": "ephemeral"}},   # breakpoint after the tool block
]
```

Serialize the tool list deterministically — same order, same key order, every request. A dict that iterates differently between processes will quietly cost you the cache on half your traffic. Verify with `usage.cache_read_input_tokens`: a persistent zero means something in the prefix is moving.
