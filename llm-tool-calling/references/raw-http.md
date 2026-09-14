# Tool Calling Over Raw HTTP

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Use the SDK by default. Reach for raw HTTP in four cases: an OpenAI-compatible endpoint the official client handles badly, a zero-dependency environment, a language with no official SDK, or debugging — when you need to see precisely what went on the wire.

## The same weather example, as a POST

```python
import json
import os
import httpx

BASE = "https://api.openai.com/v1"
HEADERS = {
    "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
    "Content-Type": "application/json",
}

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City and country"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location", "unit"],
            "additionalProperties": False,
        },
    },
}]

messages = [{"role": "user", "content": "What's the weather in Cairo?"}]

with httpx.Client(timeout=60) as http:
    r = http.post(
        f"{BASE}/chat/completions",
        headers=HEADERS,
        json={"model": MODEL, "messages": messages, "tools": TOOLS, "tool_choice": "auto"},
    )
    r.raise_for_status()
    body = r.json()

    choice = body["choices"][0]
    message = choice["message"]
    messages.append(message)          # append the raw dict, unmodified

    if choice["finish_reason"] == "length":
        raise RuntimeError("truncated before the tool call completed")

    for call in message.get("tool_calls") or []:
        args = json.loads(call["function"]["arguments"])   # always a JSON string
        try:
            result = TOOL_REGISTRY[call["function"]["name"]](**args)
        except Exception as e:
            result = {"error": str(e)}
        messages.append({
            "role": "tool",
            "tool_call_id": call["id"],
            "content": json.dumps(result),
        })

    r = http.post(
        f"{BASE}/chat/completions",
        headers=HEADERS,
        json={"model": MODEL, "messages": messages, "tools": TOOLS},
    )
    print(r.json()["choices"][0]["message"]["content"])
```

**Append the assistant message verbatim.** Reconstructing it field by field is how `tool_calls` entries get dropped, reordered, or stripped of provider-specific fields the API needs on the next turn. Take the dict you were given and push it onto the list.

## Anthropic, same shape, different envelope

```python
HEADERS = {
    "x-api-key": os.environ["ANTHROPIC_API_KEY"],
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

payload = {
    "model": MODEL,
    "max_tokens": 1024,                 # required on every Anthropic request
    "tools": [{
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    }],
    "messages": [{"role": "user", "content": "What's the weather in Cairo?"}],
}

r = httpx.post("https://api.anthropic.com/v1/messages", headers=HEADERS, json=payload)
```

Differences that matter at the wire level: no `function` wrapper, `input_schema` rather than `parameters`, `max_tokens` is mandatory, the API version goes in a header, and results come back as content blocks rather than a `tool_calls` array. Full treatment in `anthropic-format.md`.

## What to actually look at when debugging

```bash
curl -sS https://api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d @request.json | jq '.choices[0]'
```

Keep the request in a file. It makes the payload diffable, which is the whole point of dropping to curl.

Four things worth checking by eye, in order of how often they're the answer:

1. **Did `strict` survive?** Some gateways drop unknown fields. If the response echoes the tool with `strict: false`, or your schema was silently normalized, you do not have the guarantee you think you have.
2. **Is `arguments` valid JSON?** If it is truncated, check `finish_reason` before blaming the model.
3. **Do the `tool_call_id` values line up?** One tool message per call, matching ids, nothing extra.
4. **What's the token accounting?** `usage.prompt_tokens` tells you what the tool definitions actually cost. It is usually higher than people guess, and it is charged on every request.

## Streaming

Tool calls arrive in fragments. Each delta carries an `index`; accumulate the `arguments` string per index and parse once the stream closes.

```python
buffers = {}   # index -> {"id": str, "name": str, "arguments": str}

for line in stream_sse(response):
    delta = line["choices"][0]["delta"]
    for tc in delta.get("tool_calls") or []:
        buf = buffers.setdefault(tc["index"], {"id": "", "name": "", "arguments": ""})
        if tc.get("id"):
            buf["id"] = tc["id"]
        fn = tc.get("function") or {}
        if fn.get("name"):
            buf["name"] = fn["name"]
        buf["arguments"] += fn.get("arguments", "")

calls = [json.loads(b["arguments"]) for b in buffers.values()]   # only after the stream ends
```

Do not attempt to parse partial `arguments` mid-stream. Strict mode guarantees the *complete* output conforms; a prefix of valid JSON is not valid JSON.

## Retries

The SDKs retry 408, 409, 429, and 5xx with backoff by default. On raw HTTP you own that.

```python
RETRYABLE = {408, 409, 429, 500, 502, 503, 504}

for attempt in range(4):
    r = http.post(url, headers=HEADERS, json=payload)
    if r.status_code not in RETRYABLE:
        break
    wait = float(r.headers.get("retry-after", 2 ** attempt))
    time.sleep(wait)
```

Honor `retry-after` when present. Never retry a 400 — the payload is wrong and will be wrong again. Retrying a request that already executed a side-effecting tool is a different problem entirely; make the tools idempotent or key them on a request id.
