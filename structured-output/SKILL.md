---
name: structured-output
description: Use whenever an LLM's response itself must be structured data rather than prose — extracting fields from a document, email, invoice, or transcript; classifying text; scoring or labeling content; converting unstructured input into records for a database or API; or generating a config or a plan. Use it wherever code prompts for JSON and parses the response, strips markdown fences off model output, or retries on parse failures. Do not use framework output parsers unless asked by name.
metadata:
  version: "1.0"
---

# Structured Output

> **Provider-neutral.** The practice here applies to any LLM provider. Code samples name one provider's syntax to stay concrete; equivalents exist elsewhere under different names, and genuinely provider-specific features are labelled where they appear.
>
> **Verify before you build.** Endpoint shapes, parameter names, limits, and model support all move. Search the provider's current API reference before relying on any of them. If something here is stale, make the *smallest* edit that corrects it — replace the outdated token, leave the surrounding argument intact.

## Core principle

When you need the model's answer as structured data, pass a JSON Schema in the request and turn on strict mode. The provider constrains generation so the response conforms to your schema. You parse it directly — no fence-stripping, no regex, no retry loop.

This is a different API feature from tool calling, and it is the right one when the model is *answering you* rather than *calling something*. Both put a schema in the payload; they differ in where the structured data comes back and what it means.

Structured output is not a reliability patch you bolt on. It replaces an entire category of code — the JSON extractor, the validator, the retry-on-malformed loop — with a request parameter.

## Avoid / Prefer

| Avoid | Prefer |
|---|---|
| Prompt for JSON, then parse | Schema in the request, strict mode on |
| JSON mode (`json_object`) | JSON Schema response format |
| A forced single tool call to get data back | The structured output feature |
| Output-parser and retry-on-malformed wrappers | Direct parse of a conformant response |
| Optional by omission from `required` | Nullable union, every property required |
| Abbreviated field names | Descriptive names with descriptions |
| Treating conformance as correctness | Evals on extraction accuracy |

Every row is a default, and the sections below name the case where each one is the wrong call.

## Minimal pattern

```text
Need structured JSON?
    |
    v
Use native structured output
    |
    v
Validate the schema
    |
    v
Handle refusal / truncation
    |
    v
Only add parsing if measurement shows it is necessary
```

Everything below is the deep dive: when each step is wrong, and what to do instead.

## Structured output or tool calling?

The provider guidance is consistent across vendors and simple to apply:

**Use tool calling** when you are connecting the model to functions, systems, or data in your application — the model decides whether to act and with what arguments.

**Use structured output** when you want to shape how the model responds to you or your user — extraction, classification, moderation, generating a payload for your UI.

If your code forces a tool call with `tool_choice: "required"` and a single tool, purely to get structured data back, you want structured output instead. That pattern was a workaround from before structured output existed.

The two are independent and can be combined in one request on providers that support it — Anthropic documents using JSON output and strict tool use together, where strict tools guarantee the arguments passed to your functions and JSON output guarantees the shape of the final answer. Check your provider before relying on the combination.

## When to use this skill

- Extracting fields from documents, emails, invoices, transcripts, resumes, or logs
- Classification, moderation, sentiment, scoring, tagging, routing
- Turning unstructured input into rows, records, or API payloads
- Generating structured artifacts the application consumes directly (UI trees, configs, plans)
- Any existing code that prompts for JSON and parses the response — replace it
- Any code that strips ` ```json ` fences, regexes a JSON blob out of prose, or retries on `JSONDecodeError`
- Code using `response_format: {"type": "json_object"}` — that is JSON mode, which is weaker; see below

## Do this: extraction with a Pydantic schema

```python
from pydantic import BaseModel
from openai import OpenAI

MODEL = "..."  # any model supporting structured outputs
client = OpenAI()

class Invoice(BaseModel):
    invoice_number: str
    issue_date: str
    total_amount: float
    customer_name: str

completion = client.chat.completions.parse(
    model=MODEL,
    messages=[
        {
            "role": "system",
            "content": "Extract invoice fields from the supplied text.",
        },
        {"role": "user", "content": invoice_text},
    ],
    response_format=Invoice,
)

choice = completion.choices[0]

# Always handle these two before touching the payload — see below.
if choice.finish_reason == "length":
    raise ValueError("Response truncated; raise max_completion_tokens")
if choice.message.refusal:
    raise ValueError(f"Model refused: {choice.message.refusal}")

invoice = choice.message.parsed  # a typed Invoice instance
```

The `parse()` helper converts your Pydantic model to JSON Schema, sends it, and validates the response back into a typed object. Under the hood this is `response_format: {"type": "json_schema", "json_schema": {"name": ..., "strict": true, "schema": ...}}` — see `references/raw-schemas.md` for the hand-written version.

Pydantic earns its place here in a way it does not in tool calling. In tool calling, the arguments go straight into a function you already wrote with typed parameters. In extraction, the structured result *is* the thing your application carries around — so getting a typed domain object back rather than a `dict[str, Any]` is the point, not a convenience.

TypeScript uses Zod the same way, via `zodResponseFormat()` (Chat Completions) or `zodTextFormat()` (Responses API). Ruby uses Sorbet `T::Struct`, and Java, Go, C#, and PHP have equivalent native-type helpers.

## Provider parameter shapes

The concept is identical everywhere; the parameter names are not. These have moved recently — verify against current docs.

| Provider / API | Parameter |
|---|---|
| OpenAI Chat Completions | `response_format: {"type": "json_schema", "json_schema": {...}}` |
| OpenAI Responses | `text: {"format": {"type": "json_schema", ...}}` |
| Anthropic Messages | `output_config: {"format": {"type": "json_schema", "schema": {...}}}` |

Anthropic's Python SDK offers `client.messages.parse()` with a Pydantic model, returning `response.parsed_output`, plus a `transform_schema()` helper for when you need to adjust a generated schema before sending. Anthropic's parameter was `output_format` during beta and moved to `output_config.format` at GA; the old field and beta header are accepted for a transition period, but the Python SDK raises a `TypeError` if you pass `output_format` to `beta.messages.create()`.

## Schema rules for strict mode

Strict mode rejects schemas that break these rules, so get them right up front:

**`additionalProperties: false` on every object** — not just the root, every nested object.

**Every property must be in `required`.** You cannot express optional by omitting from `required`. Use a nullable union instead:

```python
# Pydantic
class Extraction(BaseModel):
    category: str
    notes: str | None      # Pydantic v2 emits {"anyOf": [{"type": "string"}, {"type": "null"}]}
```

The model returns `null` when the field doesn't apply, and your code handles absence explicitly. This is better than an omitted key anyway — you can tell "not present in the source" from "the model forgot."

**Root cannot be `anyOf`.** Wrap it in an object.

**Nesting is capped** (five levels on OpenAI-compatible). Flatten where you can.

**Recursion works** via `$ref: "#"` for root recursion or `$defs` for named subschemas. Pydantic needs `Model.model_rebuild()` to enable recursive types.

**Complexity limits apply.** Anthropic caps optional parameters and union-typed parameters across all strict schemas in a request; union types are the expensive ones because they multiply out during grammar compilation. Exceeding the limits returns a 400.

## What is enforced, and what is not

Same boundary as in tool calling: **structure is constrained, content is not.**

Enforced: types, `enum` membership, `required`, object shape, arrays, nesting, nullable unions.

Not reliably enforced: `minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, `maxItems`, `pattern`, `format`, `multipleOf`, `uniqueItems`. Support varies by provider and moves over time. Anthropic's SDKs strip unsupported constraints, fold the constraint text into the field description ("Must be at least 100"), and then validate the response against your original schema client-side — so the check happens after generation, not during it. OpenAI's SDK has done the same for several keywords.

Practical upshot: write value constraints in your Pydantic model anyway — you get client-side validation for free, and the constraint text reaches the model through the description. Just don't assume the model was *prevented* from violating them.

**Schema compliance is not accuracy.** The provider guarantees the shape, not the truth. A perfectly-formed `Invoice` with the wrong `total_amount` is a fully successful structured output. Evals are still your job.

## The two failure modes you must handle

Strict mode guarantees conformance *except* in two cases, and production code that ignores them will crash on real traffic.

**Refusal.** The model can still decline for safety reasons, and the refusal takes precedence over your schema. OpenAI returns a separate `message.refusal` string; Anthropic returns `stop_reason: "refusal"` with a 200 status, and you are billed for the tokens. Check for it before parsing and treat it as a first-class error path — log it, and have a fallback (degraded response, human escalation, different prompt).

**Truncation.** If generation hits the token limit mid-object, the output is incomplete and will not match your schema. Check `finish_reason == "length"` (OpenAI) or `stop_reason == "max_tokens"` (Anthropic) and retry with a higher limit. Extraction schemas with long string fields hit this more often than people expect.

Both checks belong in every call site. Wrap them in a helper rather than repeating them.

## Don't do this

**JSON mode.** `response_format: {"type": "json_object"}` guarantees syntactically valid JSON and nothing about the shape. It is the previous generation of this feature and providers now recommend structured outputs over it wherever supported. If you see JSON mode in a codebase, upgrade it.

**Prompting for JSON and parsing.** A system prompt saying "respond only with JSON matching this format," followed by `json.loads()` on the raw text, is the pattern structured output exists to delete. It fails on markdown fences, preambles ("Sure! Here's your JSON:"), trailing commas, and truncation.

**Output-parser abstractions.** Framework output parsers, retry-parsers, and fixing-parsers are all built around the assumption that the model's output might not match the schema. With strict mode that assumption is false, and the abstraction is overhead plus an upgrade treadmill. Instructor is the same story for structured extraction specifically: it wraps retry-and-validate logic around a call that no longer needs retrying.

**Forcing a single tool call to get structured data.** Use the structured output feature instead.

## Common pitfalls

**Not handling refusals and truncation.** The two cases above. This is the single most common production bug in structured-output code.

**Assuming valid means correct.** Conformance is not accuracy. Build evals.

**Vague field names with no descriptions.** Field names and descriptions are prompt surface — the model reads them to decide what goes in each slot. `amt` extracts worse than `total_amount_usd` with a description. Provider guidance is explicit: name keys clearly and intuitively, write clear titles and descriptions for important keys, and use evals to find the structure that works best.

**No "not found" path.** Extraction schemas that require every field force the model to invent values when the source doesn't contain them. Make genuinely-optional fields nullable so the model has a legitimate way to say "absent."

**Enum casing.** Structured outputs do not guarantee the capitalization of `enum` and `const` values — you may get a value differing from your schema only in case. Compare case-insensitively, and never define enum members that differ only by capitalization.

**Property order surprises.** Anthropic orders required properties first, then optional ones, regardless of your schema's declaration order. If output order matters to your parsing, mark everything required or handle the reordering.

**Schema churn invalidating caches.** Strict mode compiles your schema to a grammar and caches it (24 hours from last use on Anthropic). Changing the schema recompiles, adding latency to the first call. Changing `output_config.format` also invalidates the prompt cache for that thread. Don't build schemas dynamically per-request unless you need to.

**Forgetting the injected prompt.** Providers add a system prompt describing the expected format when structured outputs are on. Your input token count goes up slightly, and it costs tokens like any other system prompt.

**Putting sensitive data in the schema.** Schemas are cached separately from message content and do not receive the same protections. Anthropic's docs are explicit that PHI must not appear in schema property names, enum values, const values, or pattern regexes — only in message content. The same caution applies to any regulated or secret data.

**Feature incompatibilities.** On Anthropic, JSON outputs are incompatible with citations (returns 400) and with message prefilling. Structured outputs do work with streaming, batch processing, and token counting.

## When to break the rules

- **The output genuinely is prose.** Don't force a schema onto a summary or an explanation just because you can. `{"answer": "<three paragraphs>"}` is a schema doing nothing.
- **Your model doesn't support it.** Older or smaller models may lack structured output. Then you do need prompt-and-parse with validation and retry — write it explicitly rather than pulling in a framework.
- **You need a JSON Schema feature strict mode rejects**, and the expressiveness matters more than the guarantee.
- **Exploratory prototyping** where you don't yet know the shape.

## Success criteria

You applied this correctly if these move on the same labelled set, measured before and after:

- **Parse-failure rate.** Fence-stripping, `JSONDecodeError`, and regex-extraction fallbacks should go to zero. If they don't, strict mode is being rejected or silently downgraded somewhere.
- **Field-level extraction accuracy** against hand-labelled ground truth — the number strict mode does *not* move, and the one that decides whether the feature actually works. One criterion per field group rather than one blended score: `evals-before-shipping/references/custom-metrics.md`.
- **Invented-value rate on absent fields** — the share of records where a field missing from the source came back non-null. Making genuinely optional fields nullable should drive this down; a schema that requires everything hides it.
- **Unhandled refusal and truncation counts in production logs.** Both should be zero, because both should now be explicit branches rather than uncaught exceptions.
- **Tokens and latency per successfully extracted record.** Deleting the retry loop reduces both; building schemas per request quietly gives it back through grammar-cache misses.

If none of these move, the rewrite bought nothing on that task — the old parser was not the bottleneck, and the accuracy problem is somewhere else.

## References

- `references/raw-schemas.md` — hand-written JSON Schema instead of Pydantic/Zod, and the exact payload shapes per provider
- `references/extraction-patterns.md` — schema design for extraction: nullable fields, confidence scores, provenance, multi-record output
- `references/classification-patterns.md` — enums, multi-label, abstention, and calibration
- `references/failure-handling.md` — a reusable wrapper covering refusal, truncation, and validation
- `references/vs-tool-calling.md` — worked examples of the same task done both ways, and why each belongs where it does