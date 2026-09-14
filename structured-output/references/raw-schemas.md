# Hand-Written JSON Schema

> **Verify before you build.** Parameter names, limits, and model support named below move between releases. Check the provider's current API reference before relying on them, and correct any drift with the smallest possible edit.

Pydantic and Zod are the default because the typed object is the deliverable. Write the schema by hand when the shape is dynamic (built from a config or a database table), when you are in a language without a helper, when you need a JSON Schema feature the model generator won't emit, or when you are debugging and need to see exactly what shipped.

## OpenAI Chat Completions

```python
schema = {
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string"},
        "issue_date": {"type": "string", "description": "ISO 8601, YYYY-MM-DD"},
        "total_amount": {"type": "number"},
        "customer_name": {"type": "string"},
        "notes": {"type": ["string", "null"]},
    },
    "required": ["invoice_number", "issue_date", "total_amount", "customer_name", "notes"],
    "additionalProperties": False,
}

completion = client.chat.completions.create(
    model=MODEL,
    messages=[...],
    response_format={
        "type": "json_schema",
        "json_schema": {"name": "invoice", "strict": True, "schema": schema},
    },
)

choice = completion.choices[0]
if choice.finish_reason == "length":
    raise ValueError("truncated")
if choice.message.refusal:
    raise ValueError(choice.message.refusal)

data = json.loads(choice.message.content)   # a string here, not a parsed object
```

Note `name` is required and `strict` sits beside `schema`, both inside `json_schema`. With the raw form you get a JSON string back and parse it yourself — that is the only thing `parse()` was doing for you besides validation.

## OpenAI Responses

```python
response = client.responses.create(
    model=MODEL,
    input=[...],
    text={
        "format": {
            "type": "json_schema",
            "name": "invoice",      # flattened: name and strict are siblings of type
            "strict": True,
            "schema": schema,
        }
    },
)
```

Incomplete responses surface as `status: "incomplete"` with `incomplete_details.reason == "max_output_tokens"` rather than a `finish_reason`. Check the field your API actually has.

## Anthropic Messages

```python
response = client.messages.create(
    model=MODEL,
    max_tokens=4096,
    output_config={"format": {"type": "json_schema", "schema": schema}},
    messages=[...],
)

if response.stop_reason == "refusal":
    raise ValueError(response.stop_details)
if response.stop_reason == "max_tokens":
    raise ValueError("truncated")

data = json.loads(response.content[0].text)
```

No `name` field, no `strict` flag — the format *is* the constraint. `max_tokens` is required. The older top-level `output_format` parameter is superseded by `output_config.format`.

## Validating anyway

Raw schemas skip the client-side validation step the SDK helpers give you. Put it back — it is three lines and it catches provider divergence:

```python
from jsonschema import validate
validate(instance=data, schema=schema)
```

This matters most on the value constraints. `minimum`, `maxLength`, and `pattern` are not reliably enforced during generation; several SDKs strip them before sending and check afterward. Doing it yourself restores that check.

## Building schemas dynamically

Legitimate: the shape genuinely comes from configuration.

```python
def extraction_schema(fields: list[Field]) -> dict:
    props = {f.name: {"type": [f.json_type, "null"], "description": f.hint} for f in fields}
    return {
        "type": "object",
        "properties": props,
        "required": sorted(props),          # deterministic order — see below
        "additionalProperties": False,
    }
```

Two costs you are accepting:

**Grammar recompilation.** Providers compile the schema into a grammar and cache it — Anthropic for up to 24 hours from last use. A schema that differs per request recompiles every time, adding first-call latency to every call.

**Cache invalidation.** Changing `output_config.format` invalidates the prompt cache for that thread.

So: cache the generated schema by a hash of its inputs, and **serialize deterministically** — sorted keys, stable field order. A dict that iterates differently between processes produces a byte-different schema and silently costs you both caches on half your traffic.

```python
@lru_cache(maxsize=256)
def schema_for(config_key: str) -> str:
    return json.dumps(extraction_schema(FIELDS[config_key]), sort_keys=True)
```

## Schema rules, condensed

Strict mode rejects violations at request time, which is the good case — you find out immediately.

| Rule | Detail |
|---|---|
| `additionalProperties: false` | Every object, not just the root |
| Everything in `required` | Optional is expressed as a nullable type, never by omission |
| Root cannot be `anyOf` | Wrap it in an object |
| Nesting capped | Five levels on OpenAI-compatible |
| Recursion | `$ref: "#"` for root, `$defs` for named subschemas; no external `$ref` URLs |
| Unions cost | `anyOf` multiplies out during grammar compilation and counts against Anthropic's per-request complexity limits |

Unsupported-or-stripped keywords, consistently across providers: `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `minLength`, `maxLength`, `pattern`, `format`, `minItems`/`maxItems` beyond trivial cases, `uniqueItems`, `minProperties`, `maxProperties`.

## Recursion

```python
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "children": {"type": "array", "items": {"$ref": "#"}},
    },
    "required": ["name", "children"],
    "additionalProperties": False,
}
```

Works on OpenAI-compatible strict mode. Anthropic's documented JSON Schema subset does not support recursive schemas — flatten to a node list with parent references instead:

```python
{"nodes": [{"id": "n1", "parent_id": None, "name": "root"},
           {"id": "n2", "parent_id": "n1", "name": "child"}]}
```

Reassemble the tree in your code. This is often better anyway: unbounded recursion is also unbounded token generation, and a flat list with an id scheme is easier to validate.

## Keep sensitive data out

Compiled schemas are cached separately from message content and do not receive the same protections. Anthropic's docs state plainly that PHI must not appear in schema property names, enum values, const values, or pattern regexes. The same caution applies to any regulated or secret data — and it applies to hand-written schemas exactly as it does to generated ones. Sensitive values belong in message content.
