```python
from pydantic import BaseModel, Field

class Invoice(BaseModel):
    invoice_number: str
    issue_date: str = Field(description="ISO 8601, YYYY-MM-DD")
    total_amount_usd: float
    customer_name: str
    po_number: str | None = Field(description="Null when the invoice shows no PO.")

completion = client.chat.completions.parse(
    model=MODEL,
    messages=[{"role":"system","content":"Extract invoice fields from the supplied text."},
              {"role":"user","content":invoice_text}],
    response_format=Invoice,
    max_completion_tokens=2048,
)
choice = completion.choices[0]
if choice.finish_reason == "length":
    raise Truncated("raise max_completion_tokens")
if choice.message.refusal:
    raise Refused(choice.message.refusal)
db.insert("orders", choice.message.parsed.model_dump())
```
`po_number` is nullable because real invoices often lack one — a required field would force the model to invent a value, and strict mode would make that fabrication well-typed. The raw JSON schema sets `"additionalProperties": False` on every object.
