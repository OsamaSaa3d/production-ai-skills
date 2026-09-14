# Classification, Labeling, and Scoring

Classification is the highest-volume structured-output task in most production systems and the one where small models do best. It is also where schema design does the most work: `enum` is the one value constraint that is genuinely enforced, so almost every problem here is solved by making the legal answers explicit.

## Single label

```python
from enum import Enum
from pydantic import BaseModel, Field

class Category(str, Enum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    OTHER = "other"

class Triage(BaseModel):
    category: Category
    reasoning: str = Field(description="One sentence citing the phrase that decided it.")
```

Three rules that carry most of the accuracy:

**Put `reasoning` before the label.** Fields are generated in order, so a reasoning field declared first is *thinking* the model does before committing; declared after, it is a rationalization of a label already emitted. This is free and it measurably helps on borderline cases.

**Define the categories in the field description, not in the system prompt.** The enum values are terse tokens; `billing` does not say whether a refund request belongs there.

```python
category: Category = Field(
    description=(
        "billing: charges, invoices, refunds, payment methods. "
        "technical: errors, outages, integration problems, API failures. "
        "account: login, permissions, seats, plan changes. "
        "other: anything that fits none of the above."
    )
)
```

**Include the escape hatch.** A taxonomy with no `other` forces a wrong answer on every out-of-distribution input, and you will never see the distribution shift. Count how often `other` is chosen — a rising rate is your signal that the taxonomy needs a new category.

## Enum casing

Structured outputs do not guarantee the capitalization of `enum` and `const` values. You can get a value differing from your schema only in case.

```python
category = Category(raw.lower())          # normalize, don't trust
```

Never define enum members that differ only by capitalization (`Open` and `open` as distinct labels). Compare case-insensitively everywhere.

## Multi-label

```python
class Labels(BaseModel):
    reasoning: str
    labels: list[Tag] = Field(
        description="All applicable tags. Empty list if none apply. "
                    "Do not include a tag unless the text supports it directly."
    )
```

`minItems`/`maxItems` are not reliably enforced — say the bound in the description and check it in code. The empty list has to be explicitly legal, in the description and in your downstream handling, or you get the same forced-answer problem as a missing `other`.

Multi-label is where "at most N" instructions matter. Without a cap, models over-tag; with "at most 3, most specific first," precision improves and you can truncate safely.

## Abstention

For anything that routes to an action, give the model a documented way to decline. It is the same mechanism as a nullable extraction field.

```python
class Decision(BaseModel):
    reasoning: str
    decision: Literal["approve", "reject", "needs_human"]
    trigger: str | None = Field(
        description="For needs_human: what specifically is unclear."
    )
```

`needs_human` is a feature, not a failure. A system with no abstention path has a 100% decision rate and an unknown error rate; one that abstains 8% of the time and is right 99% on the rest is usually the better system — and the abstentions are a labeled queue of your hard cases, which is exactly what your eval set is short of.

Tune the abstention rate with the description, not the threshold: "abstain when two categories are equally supported" gets a different rate than "abstain only when the text is unintelligible."

## Scoring

Do not ask for a float. Ask for a rubric level.

```python
class Quality(BaseModel):
    reasoning: str
    score: Literal[1, 2, 3, 4, 5] = Field(
        description=(
            "1: factually wrong or unusable. "
            "2: partially correct, major gaps. "
            "3: correct but incomplete. "
            "4: correct and complete. "
            "5: correct, complete, and well-targeted to the question."
        )
    )
```

A `float` between 0 and 1 gives you unenforced range constraints (`minimum`/`maximum` are not reliably applied), poor calibration, and clustering at round numbers. An integer enum with defined levels gives you an enforced value set and a rubric you can argue with. Use an even number of levels when you want to prevent middle-hugging.

Scores do not mean anything until calibrated: label a sample by hand, compare, and adjust the rubric text. This is the same procedure as calibrating an LLM judge — see `evals-before-shipping`.

## Hierarchical taxonomies

Two levels in one call, with the dependency spelled out:

```python
class Ticket(BaseModel):
    reasoning: str
    category: Category
    subcategory: str = Field(
        description="For billing: refund_request | invoice_question | payment_failure. "
                    "For technical: api_error | outage | integration. "
                    "For account: login | permissions | plan_change. "
                    "For other: use 'unspecified'."
    )
```

Cross-field validity (`subcategory` must be legal for `category`) cannot be expressed in a strict schema — conditional subschemas are outside the supported subset. Validate it in code:

```python
VALID = {Category.BILLING: {"refund_request", "invoice_question", "payment_failure"}, ...}
if ticket.subcategory not in VALID[ticket.category]:
    route_to_review(ticket)
```

For deep taxonomies (hundreds of leaves), two calls — coarse then fine, with the fine call's enum narrowed to the chosen branch — beats one call with a giant enum. Each call gets a genuinely enforced, small enum, and the second one is cheap.

## Few-shot examples

Classification benefits from examples more than most tasks, and the examples that help are the boundary cases:

```python
messages = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": "I was charged twice for the same subscription"},
    {"role": "assistant", "content": '{"reasoning":"Duplicate charge — a billing issue despite mentioning the subscription product.","category":"billing"}'},
    {"role": "user", "content": text},
]
```

Pull them from real misclassifications rather than inventing them. An example that demonstrates a distinction the model already makes correctly is pure token cost. Keep them stable and at the front of the prompt so they cache.

## Batch classification

Classifying N items in one call is cheaper but couples the items — one bad item can shift the whole output, and truncation loses the tail.

```python
class BatchResult(BaseModel):
    results: list[ItemResult]     # each carries the input id

class ItemResult(BaseModel):
    id: str                       # echo the input id — never rely on position
    reasoning: str
    category: Category
```

**Always carry an explicit id and match on it.** Positional alignment breaks the moment the model drops or merges an item, and it breaks silently. Verify the returned set equals the input set and re-run the missing ones individually. Keep batches modest (10–20 items) so a truncation costs one batch, not a hundred rows.

For genuinely large volumes, batch APIs (asynchronous, roughly half price) beat cramming items into one prompt.

## What to measure

Accuracy alone hides the failures that matter:

| Metric | Why |
|---|---|
| Per-class precision and recall | A 94% overall score can be 40% on your rarest, most expensive class |
| Confusion matrix | Names the specific pair to fix; usually one description line |
| Abstention rate | Drifting up means distribution shift; down means the escape hatch is too hard to reach |
| `other` rate | A rising rate is a taxonomy gap, not a model problem |
| Cost per correct classification | The number `model-selection` needs |

Classification is the task class where small models most often hold the bar. Run the suite before paying for a large model on it.
