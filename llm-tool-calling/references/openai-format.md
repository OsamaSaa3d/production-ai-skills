# OpenAI-Compatible Tool Calling: Exact Payload Shapes

This is the wire format. Every OpenAI-compatible endpoint — Azure OpenAI, vLLM, Together, Groq, Ollama, OpenRouter — accepts some subset of it. The subset is the thing that bites you; see "Compatibility is a claim, not a guarantee" at the end.

## Chat Completions request

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "What's the weather in Cairo?"}
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "strict": true,
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "City and country"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
          },
          "required": ["location", "unit"],
          "additionalProperties": false
        }
      }
    }
  ],
  "tool_choice": "auto",
  "parallel_tool_calls": true
}
```

Note the nesting: `strict` and `parameters` live *inside* `function`, not beside `type`. Putting `strict` at the top level of the tool object is the single most common shape error, and it fails silently — the field is ignored and you get non-strict behavior.

## Responses request

Same concepts, flatter shape. `function` is unwrapped, and `parameters` stays.

```json
{
  "model": "...",
  "input": [{"role": "user", "content": "What's the weather in Cairo?"}],
  "tools": [
    {
      "type": "function",
      "name": "get_weather",
      "description": "Get the current weather for a location.",
      "strict": true,
      "parameters": { "...": "..." }
    }
  ],
  "tool_choice": "auto"
}
```

Porting between the two APIs is not a rename — the message array (`messages` vs `input`), the tool shape, and the structured-output parameter (`response_format` vs `text.format`) all differ. Do it deliberately.

## The assistant response

```json
{
  "choices": [{
    "finish_reason": "tool_calls",
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\":\"Cairo, Egypt\",\"unit\":\"celsius\"}"
        }
      }]
    }
  }]
}
```

Three things to internalize:

**`arguments` is a JSON string, not an object.** Always `json.loads()` it. Never string-match on it — escaping (Unicode, forward slashes) varies by model and snapshot.

**`content` can be non-null alongside tool calls.** Models often narrate before calling. Don't assume one excludes the other.

**`finish_reason: "tool_calls"` is the loop signal.** `"stop"` means the model is done. `"length"` means truncation — and a truncated `arguments` string is invalid JSON even with strict mode on.

## Sending the result back

```json
{"role": "tool", "tool_call_id": "call_abc123", "content": "{\"temp_c\": 31, \"conditions\": \"clear\"}"}
```

Rules that are not negotiable:

- The assistant message containing the `tool_calls` must be appended to `messages` **before** the tool results. A tool result with no preceding tool call is a 400 on most providers.
- Every `tool_call_id` in the assistant message needs exactly one matching tool message. Missing one is a 400; an extra one is a 400.
- `content` must be a string. Serialize objects yourself.
- Role is `tool`. Not `user`, not `function` (the `function` role is the pre-2023 deprecated shape).

## How `tools`, `strict`, and `tool_choice` interact

| `tool_choice` | Meaning | Interaction with `strict` |
|---|---|---|
| `"auto"` (default when `tools` present) | Model picks zero, one, or many | Strict applies to whatever it calls |
| `"required"` | Must call at least one tool | Strict applies; use for "the call *is* the task" |
| `"none"` (default when no `tools`) | Never call; definitions still cost tokens | Strict irrelevant |
| `{"type": "function", "name": "f"}` | Must call `f` | Strict on `f` gives you the strongest guarantee available: this tool, valid arguments |
| `{"type": "allowed_tools", "mode": "auto", "tools": [...]}` | Restrict to a subset without resending definitions | Per-tool `strict` still governs |

`allowed_tools` is the cheap way to narrow the catalog per request: definitions stay cached, only the permitted set changes. Prefer it over rebuilding the `tools` array, which invalidates prompt caching.

Forcing a tool (`"required"` or a named function) prefills the model into a call. On some providers this suppresses the natural-language preamble entirely. If you want both a narration and a guaranteed call, use `"auto"` plus an instruction naming the tool in the user message.

## `parallel_tool_calls`

Default `true`. One assistant message may carry several `tool_calls`.

```python
if message.tool_calls:
    results = await asyncio.gather(*[run(tc) for tc in message.tool_calls])
    for tc, result in zip(message.tool_calls, results):
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": json.dumps(result),
        })
```

Append **all** the results, in one batch, before the next request. Dropping one — including a failed one, which should come back as `{"error": "..."}` rather than being omitted — leaves a dangling call.

Set `parallel_tool_calls: false` when: the calls are order-dependent (verify identity before issuing the refund), you're on a fine-tuned model where strict mode is disabled for parallel calls, or you're on a snapshot with known duplicate-call behavior. It forces exactly zero or one call per turn.

## Strict-mode schema requirements

Rejected loudly if violated, which is the good case:

- `additionalProperties: false` on **every** object, including nested ones.
- Every key in `properties` must appear in `required`.
- Optional means nullable: `{"type": ["string", "null"]}` or `{"anyOf": [{"type": "string"}, {"type": "null"}]}`.
- Nesting capped at five levels.
- `$ref` / `$defs` for recursion; no external `$ref` URLs.

What's enforced is structure. `minimum`, `maxLength`, `pattern`, `format` and friends are best-effort at most — several SDKs strip them before sending and validate client-side afterward. Write them anyway for the free client-side check and the description text they contribute, but don't build correctness on them.

## Compatibility is a claim, not a guarantee

"OpenAI-compatible" endpoints diverge in ways that don't announce themselves:

- **`strict` ignored.** The field is accepted and dropped. You get best-effort adherence with no error. Test it: send a schema with a required enum and a prompt pushing the model off it.
- **`parallel_tool_calls` unsupported.** Some servers emit one call per turn regardless.
- **Prompt-templated tools.** Gateways that front models without native tool support can render your tools into the prompt as text and parse the reply. The response is shaped like a tool call and carries none of the guarantees. See `model-selection` for gating on advertised capability before you send.
- **`tool_call_id` format.** Don't parse or generate these. Echo back exactly what you received.

Verify on your actual endpoint with a deliberately adversarial test case, once, at integration time. It is a ten-minute check that saves an intermittent production bug.
