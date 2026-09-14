# Schema Design for Extraction

Strict mode guarantees you get an object matching your schema. It guarantees nothing about whether the values are in the document. Every pattern here exists to make the difference visible.

## The "not found" path is the whole game

An extraction schema where every field is required and non-nullable forces the model to invent a value when the source doesn't have one. There is no legal way for it to say "absent," so it fills the slot. Strict mode makes that fabrication *well-typed*, which is worse than a parse error — nothing downstream can tell.

```python
class Invoice(BaseModel):
    invoice_number: str
    issue_date: str
    total_amount: float
    po_number: str | None        # genuinely optional on many invoices
    customer_vat_id: str | None
```

Rule: **a field is nullable if a real document might not contain it.** That is a question about your documents, not about your database schema. A column that is `NOT NULL` downstream still needs a nullable extraction field plus an explicit decision about what to do with the null.

Under strict mode `str | None` renders as `{"type": ["string", "null"]}` and the field still appears in `required` — the model must emit the key, and `null` is a legal value for it. That is exactly the shape you want: "the model considered this field and found nothing" is distinguishable from "the model forgot."

## Field names and descriptions are prompt surface

The model reads them to decide what goes in each slot. They are the cheapest accuracy lever in extraction.

```python
class LineItem(BaseModel):
    description: str = Field(description="The item description exactly as printed")
    quantity: int
    unit_price_usd: float = Field(
        description="Price per unit in USD. Convert from other currencies "
                    "using the rate printed on the invoice; if no rate is "
                    "printed, use the original currency and set currency_note."
    )
    currency_note: str | None = Field(
        description="Set only when unit_price_usd could not be converted to USD."
    )
```

`amt` extracts worse than `total_amount_usd`. Ambiguity you resolve in a description is ambiguity the model doesn't resolve by guessing. Note the pattern in `unit_price_usd`: the description names the edge case *and* the field that handles it, so the escape hatch is discoverable.

## Provenance: make claims checkable

For anything that gets audited, reviewed, or disputed, extract the evidence alongside the value.

```python
class ExtractedField(BaseModel):
    value: str | None
    source_text: str | None = Field(
        description="The exact substring from the document supporting this value. "
                    "Null if the value is not present in the document."
    )

class Contract(BaseModel):
    party_a: ExtractedField
    termination_notice_days: ExtractedField
```

Then verify in code — this is the part that makes it worth the tokens:

```python
def grounded(field: ExtractedField, document: str) -> bool:
    if field.value is None:
        return field.source_text is None
    return field.source_text is not None and field.source_text in document
```

A `source_text` that is not a substring of the document is a fabrication you caught mechanically, with no judge model and no eval set. It is the single highest-value check in extraction. Normalize whitespace before comparing, and expect to allow near-matches for PDFs where extraction mangles spacing.

## Confidence scores: only with a decision attached

A `confidence: float` field is self-reported and poorly calibrated. It is worth having only if a number crossing a threshold changes what happens.

```python
class Extraction(BaseModel):
    value: str | None
    confidence: Literal["high", "medium", "low"] = Field(
        description=(
            "high: stated explicitly and unambiguously. "
            "medium: inferred from context. "
            "low: a guess — prefer null over a low-confidence value."
        )
    )
```

Coarse ordinal buckets with defined meanings beat a float. `0.87` invites false precision; nobody can say what distinguishes it from `0.83`. Three named levels the model can actually apply give you a routing signal:

```python
if result.confidence == "low" or result.value is None:
    queue_for_human_review(doc_id, result)
```

Calibrate before you trust the threshold: label a few hundred extractions by hand and measure the actual accuracy at each level. If "high" is right 82% of the time, your routing rule is built on sand. Note that `minimum`/`maximum` are not reliably enforced anyway, which is one more reason enums beat floats here.

## Multiple records from one document

Wrap the list — the root cannot be an array under strict mode, and you want somewhere to put document-level fields anyway.

```python
class LineItem(BaseModel):
    description: str
    quantity: int
    unit_price: float

class InvoiceExtraction(BaseModel):
    invoice_number: str
    line_items: list[LineItem]
    line_item_count: int = Field(
        description="Number of line items found. Must equal the length of line_items."
    )
```

The redundant count is a cheap self-check: `len(result.line_items) != result.line_item_count` catches truncated or partially-hallucinated lists without a second call.

`minItems`/`maxItems` are not reliably enforced, so express list bounds in the description and check them yourself. If a document can produce hundreds of rows, the real risk is truncation — see below.

## Truncation is the extraction-specific failure

Extraction hits the token ceiling far more often than classification does, because output size scales with document size. A truncated object does not match your schema and will not parse.

Three mitigations, in order:

1. **Size `max_tokens` from the document**, not from a fixed constant. Estimate output tokens as a function of input length and add headroom.
2. **Don't echo the document.** A `source_text` per field is worth it; re-emitting whole paragraphs is not. Long verbatim string fields are the usual cause.
3. **Chunk and merge** for genuinely large documents: extract per page or per section, then reconcile. Reconciliation needs its own rule for conflicts — usually "first non-null wins" plus a flag when two chunks disagree.

Always check the truncation signal (`finish_reason == "length"`, `stop_reason == "max_tokens"`, or `incomplete_details.reason`) before parsing. See `failure-handling.md`.

## Dates, numbers, and other formats

Formats are conventions, and conventions belong in descriptions and examples, since `format` and `pattern` are not reliably enforced.

```python
issue_date: str = Field(
    description="ISO 8601 date, YYYY-MM-DD. If the document shows an ambiguous "
                "numeric date (03/04/2026), use the format indicated elsewhere "
                "in the document; if still ambiguous, set date_ambiguous to true."
)
date_ambiguous: bool
```

Then parse strictly in code and treat a parse failure as an extraction failure, not a crash. Prefer extracting the raw string *and* the normalized value when the original matters for audit.

## Property order

Anthropic orders required properties before optional ones in its output, regardless of your declaration order. Don't build parsing that depends on key order — you should be going through a validator anyway, which makes order irrelevant.

## Evaluate the fields separately

An extraction eval scored as "did the whole object match" tells you almost nothing. Score per field:

```text
field                   | exact | null-correct | fabricated
------------------------|-------|--------------|------------
invoice_number          | 0.98  | n/a          | 0.00
total_amount            | 0.94  | n/a          | 0.01
po_number               | 0.71  | 0.88         | 0.09     ← look here
customer_vat_id         | 0.90  | 0.95         | 0.00
```

The **fabricated** column — a non-null value where the ground truth is null — is the one that matters most and the one a single accuracy number hides. A field with 9% fabrication needs a better description or a nullable type, not a better model. Build the suite with `evals-before-shipping`.
