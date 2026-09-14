# Handling the Failure Modes

Strict mode guarantees conformance except in two cases, and both appear in real traffic. Write the wrapper once and call it everywhere; the alternative is these four lines forgotten at one call site out of twelve.

## The two cases

**Refusal.** The model declines for safety reasons and the refusal takes precedence over your schema. It is not an error status — you get a 200 and you are billed for the tokens.

**Truncation.** Generation hit the token ceiling mid-object. The output is a valid *prefix* of conforming JSON, which is not conforming JSON.

Neither raises. Both produce a response object your parse will fail on, or worse, one your parse will half-succeed on.

## Provider signals

| | OpenAI Chat Completions | OpenAI Responses | Anthropic Messages |
|---|---|---|---|
| Refusal | `choice.message.refusal` (a string) | a `refusal` content part | `stop_reason == "refusal"`, with `stop_details.category` |
| Truncation | `choice.finish_reason == "length"` | `status == "incomplete"`, `incomplete_details.reason == "max_output_tokens"` | `stop_reason == "max_tokens"` |
| Success | `finish_reason == "stop"` | `status == "completed"` | `stop_reason == "end_turn"` |

Check `stop_reason`/`finish_reason` **before** reading content. On Anthropic, `stop_details` is populated only when `stop_reason == "refusal"` and is `null` otherwise, so guard before reading it.

## The wrapper

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Type
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

class Refused(Exception):
    def __init__(self, message: str, category: str | None = None):
        super().__init__(message)
        self.category = category

class Truncated(Exception): ...
class Invalid(Exception): ...

@dataclass
class Parsed(Generic[T]):
    value: T
    usage: dict
    attempts: int


def extract(schema: Type[T], messages: list[dict], *, max_tokens: int = 4096,
            max_retries: int = 1) -> Parsed[T]:
    attempt = 0
    while True:
        attempt += 1
        completion = client.chat.completions.parse(
            model=MODEL,
            messages=messages,
            response_format=schema,
            max_completion_tokens=max_tokens,
        )
        choice = completion.choices[0]
        usage = completion.usage.model_dump()

        if choice.message.refusal:
            log.warning("structured_refusal", schema=schema.__name__,
                        refusal=choice.message.refusal)
            raise Refused(choice.message.refusal)

        if choice.finish_reason == "length":
            log.warning("structured_truncated", schema=schema.__name__, cap=max_tokens)
            if attempt <= max_retries:
                max_tokens *= 2            # the one retry that is actually justified
                continue
            raise Truncated(f"still truncated at max_tokens={max_tokens}")

        if choice.message.parsed is None:
            raise Invalid("no parsed output and no refusal — inspect the raw response")

        return Parsed(choice.message.parsed, usage, attempt)
```

Four decisions embedded in that:

**Refusal is not retried.** A retry of the same prompt gets refused again and costs you tokens. It is a routing decision, not a transient failure.

**Truncation is retried once, with a doubled cap.** This is the only retry in structured output that reliably works, because the cause is known and the fix is mechanical. Retrying more than once means your cap estimate is wrong — fix the estimate.

**Both are logged before raising.** The refusal rate and the truncation rate are metrics you want on a dashboard; they are your early warning that input distribution has shifted.

**Distinct exception types.** The caller routes a refusal to human escalation and a truncation to the on-call engineer. One generic `ExtractionError` collapses that distinction at exactly the moment you need it.

## What a refusal should do

Refusals reach production through inputs you did not anticipate — a document containing content that trips a classifier, a user pasting something unexpected. Options, in the order to prefer them:

1. **Degrade explicitly.** Return a documented "could not process" result the downstream system understands. Never return an empty or default-valued object that looks like a successful extraction.
2. **Escalate to a human** with the input attached, if the workflow has a review queue.
3. **Re-prompt with narrowed scope** — extract fewer fields, or only the non-sensitive ones — where the refusal is plausibly about one part of the task.

Do not silently swallow it, and do not fall back to prompt-and-parse on a different model to "get an answer." If the model declined, the answer is not obviously yours to route around.

On Anthropic's Fable/Opus tier, refusals carry a category in `stop_details` and the API offers server-side fallbacks (`betas: ["server-side-fallback-2026-07-01"]` with `fallbacks: "default"`) that route by category automatically. If you are on those models, use it rather than hand-rolling a fallback chain.

## Validation beyond the schema

Conformance is structural. Everything the schema cannot enforce goes here:

```python
def validate_invoice(inv: Invoice, document: str) -> list[str]:
    problems = []
    if inv.total_amount is not None and inv.total_amount < 0:
        problems.append("negative total")                  # minimum not enforced
    if inv.issue_date and not ISO_DATE.fullmatch(inv.issue_date):
        problems.append(f"bad date format: {inv.issue_date}")   # pattern not enforced
    if inv.line_items and abs(sum(li.total for li in inv.line_items)
                              - (inv.total_amount or 0)) > 0.01:
        problems.append("line items do not sum to total")   # cross-field: never enforceable
    return problems
```

The third check is the interesting one. Cross-field consistency cannot be expressed in a strict schema at all, and it is the check most likely to catch a fabricated value. Look for arithmetic identities, date orderings, and count fields in your domain — each one is a free hallucination detector.

Route failures rather than raising: a well-formed object that fails a business rule is a review-queue item, not a 500.

## Retry policy, complete

| Failure | Retry? | How |
|---|---|---|
| Truncation | Yes, once | Double `max_tokens` |
| Refusal | No | Route to the refusal path |
| Rate limit / 429 | Yes | Backoff, honor `retry-after` (the SDKs do this) |
| 5xx / connection | Yes | Backoff (the SDKs do this) |
| 400 on schema | No | Your schema is invalid; fix it |
| Passes schema, fails business rule | No | Review queue |
| "The answer was wrong" | No | This is an eval problem, not a retry problem |

The last row is the one to internalize. Retrying a well-formed wrong answer is how a structured-output codebase grows back the retry loop the feature was supposed to delete. Fix it with better field descriptions, examples, or a different model — measured, per `evals-before-shipping`.

## Metrics worth alerting on

| Metric | Meaning of a change |
|---|---|
| Refusal rate | A step change means an input-distribution shift or a model update |
| Truncation rate | Documents got bigger, or a schema field grew |
| Business-rule failure rate | Accuracy regression the schema cannot see |
| Null rate per field | Usually the first sign of an upstream format change |
| Cost per successful extraction | Includes retries — the number `model-selection` needs |

Null rate per field is underrated: a field that goes from 2% null to 40% null overnight is an upstream change (a new document template, a changed PDF exporter) and nothing else in your monitoring will catch it.
