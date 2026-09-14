Legal is auditing this, so extract the evidence alongside each value and verify it mechanically.

```python
class Extracted(BaseModel):
    value: str | None
    source_text: str | None = Field(description="Exact substring from the contract supporting this value. Null if absent.")

class Contract(BaseModel):
    party_a: Extracted
    party_b: Extracted
    termination_clause: Extracted

def grounded(f: Extracted, document: str) -> bool:
    if f.value is None:
        return f.source_text is None
    return f.source_text is not None and f.source_text in document

c = client.chat.completions.parse(model=MODEL, response_format=Contract,
        messages=[{"role":"user","content":contract}], max_completion_tokens=4096).choices[0]
if c.finish_reason == "length": raise Truncated()
if c.message.refusal: raise Refused(c.message.refusal)
result = c.message.parsed
for name, field in result:
    if not grounded(field, contract):
        queue_for_human_review(name, field)
```
A `source_text` that is not a substring of the document is a fabrication caught mechanically — no judge model, no eval set. It costs extra output tokens, which is worth it here and would not be for a low-stakes extraction.
